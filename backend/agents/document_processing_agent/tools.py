import os
import json
import re
import traceback
import time
import fitz  # PyMuPDF
import numpy as np
import cv2
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient

# Add project root to sys.path to allow absolute imports from /backend
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.config import load_config
from backend.agents.shared_libraries.utils import get_absolute_path, get_output_path

# Import Sentry for error tracking
try:
    from backend.sentry_config import capture_exception, capture_message, add_breadcrumb
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False
    # Fallback functions when Sentry is not available
    def capture_exception(error, extra_context=None):
        pass
    def capture_message(message, level='info', extra_context=None):
        pass
    def add_breadcrumb(message, category='custom', level='info', data=None):
        pass

# ============================================
# Tier 1 Analysis Tool: Azure OCR
# ============================================

def create_form_field_blueprint_from_azure(file_path: str) -> str:
    """
    (Primary Tool) Analyzes a document using Azure Document Intelligence to find all
    words and their coordinates. It saves the raw analysis to a JSON file for debugging and
    then applies heuristics to identify likely form field labels, creating a JSON "blueprint".
    """
    try:
        config = load_config()
        AZURE_DOC_INTEL_ENDPOINT = config.get('AZURE_DOC_INTEL_ENDPOINT')
        AZURE_DOC_INTEL_KEY = config.get('AZURE_DOC_INTEL_KEY')

        if not AZURE_DOC_INTEL_ENDPOINT or not AZURE_DOC_INTEL_KEY:
            return '{"error": "Azure Document Intelligence credentials are not configured."}'

        absolute_file_path = get_absolute_path(file_path)
        client = DocumentIntelligenceClient(
            endpoint=AZURE_DOC_INTEL_ENDPOINT, credential=AzureKeyCredential(AZURE_DOC_INTEL_KEY)
        )

        with open(absolute_file_path, "rb") as f:
            poller = client.begin_analyze_document(
                "prebuilt-layout", f.read(), content_type="application/octet-stream"
            )
        result = poller.result(timeout=600)
        
        raw_output_path = get_output_path(file_path, "_azure_raw_analysis.json")
        try:
            with open(raw_output_path, 'w') as f:
                json.dump(result.to_json(), f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save raw Azure analysis file: {e}")

        if not result.pages:
            return '{"error": "Azure did not return any pages from the document."}'

        form_fields = []
        for page_num, page in enumerate(result.pages):
            # The rest of this tool is a basic heuristic. The raw output is the most valuable part.
            # Look for words ending with ':' OR common form field patterns
            potential_labels = []
            common_field_patterns = ['name', 'address', 'phone', 'email', 'date', 'signature', 'company', 'title', 'license', 'number', 'amount', 'total', 'description']
            
            for w in page.words:
                word_text = w.content.strip().lower()
                # Original colon logic
                if w.content.strip().endswith(':'):
                    potential_labels.append(w)
                # New: look for common field patterns
                elif any(pattern in word_text for pattern in common_field_patterns) and len(word_text) > 2:
                    potential_labels.append(w)
            
            for label_word in potential_labels:
                label_text = label_word.content.strip().replace(":", "")
                if "signature" in label_text.lower(): continue
                label_poly = label_word.polygon
                label_x_coords = [label_poly[i] for i in range(0, len(label_poly), 2)]
                label_y_coords = [label_poly[i+1] for i in range(0, len(label_poly), 2)]
                
                field_x0 = max(label_x_coords) + 10
                field_y0 = min(label_y_coords) - 5
                field_x1 = page.width - 50
                field_y1 = max(label_y_coords) + 5

                if field_x1 <= field_x0: continue

                form_fields.append({
                    "field_name": label_text, "field_type": "text", "page_number": page_num + 1,
                    "coordinates": [
                        {"x": field_x0 / page.width, "y": field_y0 / page.height},
                        {"x": field_x1 / page.width, "y": field_y0 / page.height},
                        {"x": field_x1 / page.width, "y": field_y1 / page.height},
                        {"x": field_x0 / page.width, "y": field_y1 / page.height},
                    ]
                })

        if not form_fields:
            return f'{{"error": "The Azure-based heuristic analysis did not identify any potential form fields.", "raw_output_path": "{raw_output_path}"}}'

        return json.dumps({"form_fields": form_fields, "raw_output_path": raw_output_path}, indent=2)

    except Exception as e:
        return f'{{"error": "An error occurred in the Azure blueprint tool: {type(e).__name__} - {str(e)}"}}'

def create_underscore_blueprint_from_azure(file_path: str) -> str:
    """
    (Azure Underscore Tool) Uses Azure Document Intelligence to detect all text and lines,
    then specifically looks for underscore patterns (both text underscores and drawn lines)
    to identify form fields. This handles both text-based and graphics-based underscores.
    """
    try:
        config = load_config()
        AZURE_DOC_INTEL_ENDPOINT = config.get('AZURE_DOC_INTEL_ENDPOINT')
        AZURE_DOC_INTEL_KEY = config.get('AZURE_DOC_INTEL_KEY')

        if not AZURE_DOC_INTEL_ENDPOINT or not AZURE_DOC_INTEL_KEY:
            return '{"error": "Azure Document Intelligence credentials are not configured."}'

        absolute_file_path = get_absolute_path(file_path)
        client = DocumentIntelligenceClient(
            endpoint=AZURE_DOC_INTEL_ENDPOINT, credential=AzureKeyCredential(AZURE_DOC_INTEL_KEY)
        )

        with open(absolute_file_path, "rb") as f:
            # Try using prebuilt-read model for raw OCR without cleaning
            # This should preserve more of the original visual text including underscores
            poller = client.begin_analyze_document(
                "prebuilt-read", f.read(), content_type="application/octet-stream"
            )
        result = poller.result(timeout=600)
        
        print(f"[DEBUG-AZURE-RAW] Using prebuilt-read model for raw OCR")
        
        raw_output_path = get_output_path(file_path, "_azure_underscore_analysis.json")
        try:
            with open(raw_output_path, 'w') as f:
                # Convert Azure result to dict for JSON serialization
                result_dict = {
                    "model_id": result.model_id if hasattr(result, 'model_id') else "unknown",
                    "pages": []
                }
                for page in result.pages:
                    page_dict = {
                        "page_number": getattr(page, 'page_number', 0),
                        "width": getattr(page, 'width', 0),
                        "height": getattr(page, 'height', 0),
                        "words_count": len(page.words) if page.words else 0,
                        "lines_count": len(page.lines) if hasattr(page, 'lines') and page.lines else 0
                    }
                    result_dict["pages"].append(page_dict)
                json.dump(result_dict, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save raw Azure analysis file: {e}")

        if not result.pages:
            return '{"error": "Azure did not return any pages from the document."}'

        form_fields = []
        for page_num, page in enumerate(result.pages):
            print(f"[DEBUG-AZURE-UNDERSCORE] Processing page {page_num + 1}")
            print(f"[DEBUG-AZURE-UNDERSCORE] Page {page_num + 1}: Total words detected by Azure: {len(page.words) if page.words else 0}")
            
            # Debug: Show sample words to understand what Azure detects
            if page.words:
                sample_words = page.words[:10]  # First 10 words
                print(f"[DEBUG-AZURE-UNDERSCORE] Sample words from Azure:")
                for i, word in enumerate(sample_words):
                    print(f"  {i+1}. '{word.content}' (underscore: {'_' in word.content})")
            
            # Method 1: Find text-based underscores (RELAXED CRITERIA)
            text_underscore_areas = []
            underscore_words = []
            
            for word in page.words:
                # More relaxed underscore detection - any word containing underscores
                if "_" in word.content:
                    underscore_words.append(word)
                    word_poly = word.polygon
                    x_coords = [word_poly[i] for i in range(0, len(word_poly), 2)]
                    y_coords = [word_poly[i+1] for i in range(0, len(word_poly), 2)]
                    
                    text_underscore_areas.append({
                        "x0": min(x_coords), "y0": min(y_coords),
                        "x1": max(x_coords), "y1": max(y_coords),
                        "type": "text_underscore",
                        "content": word.content
                    })
            
            print(f"[DEBUG-AZURE-UNDERSCORE] Page {page_num + 1}: Found {len(underscore_words)} words with underscores")
            print(f"[DEBUG-AZURE-UNDERSCORE] Page {page_num + 1}: Found {len(text_underscore_areas)} text-based underscore areas")
            
            # Debug: Show underscore words found
            if underscore_words:
                print(f"[DEBUG-AZURE-UNDERSCORE] Underscore words found:")
                for i, word in enumerate(underscore_words[:5]):
                    print(f"  {i+1}. '{word.content}'")
            
            # Method 2: Detect drawn lines (horizontal lines that could be underscore fields)
            drawn_line_areas = []
            if hasattr(page, 'lines') and page.lines:
                for line in page.lines:
                    line_poly = line.polygon
                    x_coords = [line_poly[i] for i in range(0, len(line_poly), 2)]
                    y_coords = [line_poly[i+1] for i in range(0, len(line_poly), 2)]
                    
                    width = max(x_coords) - min(x_coords)
                    height = max(y_coords) - min(y_coords)
                    
                    # Look for horizontal lines that could be form field underlines
                    if width > 50 and height < 10 and width > height * 5:  # Horizontal line criteria
                        drawn_line_areas.append({
                            "x0": min(x_coords), "y0": min(y_coords),
                            "x1": max(x_coords), "y1": max(y_coords),
                            "type": "drawn_line",
                            "width": width, "height": height
                        })
            
            print(f"[DEBUG-AZURE-UNDERSCORE] Page {page_num + 1}: Found {len(drawn_line_areas)} drawn line areas")
            
            # Combine both types of underscore areas
            all_underscore_areas = text_underscore_areas + drawn_line_areas
            
            if not all_underscore_areas:
                print(f"[DEBUG-AZURE-UNDERSCORE] Page {page_num + 1}: No underscore patterns found")
                continue
            
            # For each underscore area, look for labels and create form fields
            for i, area in enumerate(all_underscore_areas):
                # Look for labels to the left of the underscore area
                label_x_start = max(0, area["x0"] - 200)  # Look 200 points to the left
                label_y_start = area["y0"] - 15  # Look 15 points up
                label_y_end = area["y1"] + 15    # Look 15 points down
                
                # Find words in the label area
                label_words = []
                for word in page.words:
                    word_poly = word.polygon
                    word_x = sum([word_poly[i] for i in range(0, len(word_poly), 2)]) / 4  # Center X
                    word_y = sum([word_poly[i+1] for i in range(0, len(word_poly), 2)]) / 4  # Center Y
                    
                    if (label_x_start <= word_x <= area["x0"] - 5 and 
                        label_y_start <= word_y <= label_y_end):
                        label_words.append((word.content, word_y, word_x))
                
                # Sort label words by position (top to bottom, left to right)
                label_words.sort(key=lambda w: (w[1], w[2]))
                
                # Create field name from label words
                if label_words:
                    field_name = " ".join([w[0] for w in label_words]).strip(": \n\t")
                    field_name = re.sub(r'\s+', ' ', field_name).strip()
                    # Clean up common non-field patterns
                    field_name = re.sub(r'\b(page|of|form|document|line)\b', '', field_name, flags=re.IGNORECASE).strip()
                else:
                    field_name = f"Underscore_Field_{page_num + 1}_{i + 1}"
                
                # Skip very short or signature fields
                if len(field_name) < 2 or "signature" in field_name.lower():
                    continue
                
                # Limit field name length
                field_name = field_name[:50]
                
                form_fields.append({
                    "field_name": field_name,
                    "field_type": "text",
                    "is_required": False,
                    "page_number": page_num + 1,
                    "coordinates": [
                        {"x": area["x0"] / page.width, "y": area["y0"] / page.height},
                        {"x": area["x1"] / page.width, "y": area["y0"] / page.height},
                        {"x": area["x1"] / page.width, "y": area["y1"] / page.height},
                        {"x": area["x0"] / page.width, "y": area["y1"] / page.height}
                    ],
                    "detection_method": area["type"],  # "text_underscore" or "drawn_line"
                    "azure_detected": True
                })
        
        if not form_fields:
            return f'{{"error": "No underscore-based form fields were detected by Azure.", "raw_output_path": "{raw_output_path}"}}'
        
        print(f"[DEBUG-AZURE-UNDERSCORE] Total underscore fields found: {len(form_fields)}")
        return json.dumps({
            "form_fields": form_fields, 
            "detection_method": "azure_underscore_detection",
            "raw_output_path": raw_output_path
        }, indent=2)

    except Exception as e:
        return f'{{"error": "An error occurred in Azure underscore detection: {type(e).__name__} - {str(e)}"}}'

# ============================================
# Tier 2 Analysis Tool: Underscore-Based Detection
# ============================================

def extract_underscore_fields(file_path: str) -> str:
    """
    (Primary Underscore Tool) Analyzes a PDF specifically looking for underscore patterns
    that typically indicate fillable form areas. This is more focused than the general
    CV heuristics and should be more accurate for forms with underscore field patterns.
    """
    try:
        doc = fitz.open(get_absolute_path(file_path))
        all_form_fields = []
        print(f"[DEBUG-UNDERSCORE] Document '{os.path.basename(file_path)}' has {len(doc)} pages.")

        for page_num, page in enumerate(doc):
            print(f"--- [DEBUG-UNDERSCORE] Processing Page {page_num + 1}/{len(doc)} ---")
            
            if len(page.get_text()) < 50:
                print(f"[DEBUG-UNDERSCORE] Page {page_num + 1} is sparse, skipping.")
                continue

            # Get all words that contain underscores
            underscore_words = [word for word in page.get_text("words") if "_" in word[4]]
            print(f"[DEBUG-UNDERSCORE] Page {page_num + 1}: Found {len(underscore_words)} words with underscores.")
            
            if not underscore_words:
                print(f"[DEBUG-UNDERSCORE] Page {page_num + 1}: No underscore patterns found.")
                continue

            # Group underscore words by proximity to form potential field areas
            underscore_rects = [fitz.Rect(word[:4]) for word in underscore_words]
            
            # Merge overlapping or very close underscore areas
            merged_rects = merge_overlapping_rects(underscore_rects, tolerance=10)
            print(f"[DEBUG-UNDERSCORE] Page {page_num + 1}: Merged to {len(merged_rects)} potential field areas.")

            for i, rect in enumerate(merged_rects):
                # Look for field labels to the left of the underscore area
                # Expand search area: 200px left, 10px up/down
                label_rect = fitz.Rect(rect.x0 - 200, rect.y0 - 10, rect.x0 - 5, rect.y1 + 10)
                
                # Get words in the label area
                label_words = page.get_text("words", clip=label_rect)
                label_words.sort(key=lambda w: (w[1], w[0]))  # Sort by position
                
                # Create field name from label words
                if label_words:
                    field_name = " ".join([w[4] for w in label_words]).strip(": \n\t")
                    field_name = re.sub(r'\s+', ' ', field_name).strip()
                    # Remove common non-field words
                    field_name = re.sub(r'\b(page|of|form|document)\b', '', field_name, flags=re.IGNORECASE).strip()
                else:
                    field_name = f"Field_{page_num + 1}_{i + 1}"
                
                # Skip if field name is too short or contains signature
                if len(field_name) < 2 or "signature" in field_name.lower():
                    continue
                
                # Clean up the field name
                field_name = field_name[:50]  # Limit length
                
                all_form_fields.append({
                    "field_name": field_name,
                    "field_type": "text",
                    "is_required": False,
                    "page_number": page_num + 1,
                    "coordinates": [
                        {"x": rect.x0/page.rect.width, "y": rect.y0/page.rect.height},
                        {"x": rect.x1/page.rect.width, "y": rect.y0/page.rect.height},
                        {"x": rect.x1/page.rect.width, "y": rect.y1/page.rect.height},
                        {"x": rect.x0/page.rect.width, "y": rect.y1/page.rect.height}
                    ],
                    "underscore_pattern": True  # Mark as underscore-detected
                })
        
        if not all_form_fields:
            return '{"error": "No underscore-based form fields were found in the document."}'
        
        print(f"[DEBUG-UNDERSCORE] Total fields found: {len(all_form_fields)}")
        return json.dumps({"form_fields": all_form_fields, "detection_method": "underscore_based"}, indent=2)

    except Exception as e:
        error_message = f'{{"error": "An error occurred in underscore detection: {type(e).__name__} - {str(e)}"}}'
        print(f"[DEBUG-UNDERSCORE] Exception: {error_message}")
        return error_message

# ============================================
# Tier 3 Analysis Tool: Local CV/Text Heuristics
# ============================================

def merge_overlapping_rects(rects: list, tolerance: int = 5) -> list:
    """ Merges overlapping or very close fitz.Rect objects into larger bounding boxes. """
    if not rects: return []
    sorted_rects = sorted(rects, key=lambda r: (r.y0, r.x0))
    merged = []
    current_merge_rect = sorted_rects[0]
    for i in range(1, len(sorted_rects)):
        next_rect = sorted_rects[i]
        expanded_rect = fitz.Rect(current_merge_rect)
        expanded_rect.x1 += tolerance
        expanded_rect.y1 += tolerance
        if expanded_rect.intersects(next_rect):
            current_merge_rect.include_rect(next_rect)
        else:
            merged.append(current_merge_rect)
            current_merge_rect = next_rect
    merged.append(current_merge_rect)
    return merged

def extract_fields_with_local_heuristics(file_path: str) -> str:
    """
    (High-Speed Vector Analysis Tool) Uses an advanced hybrid approach combining:
    1. Fast vector graphics extraction from PDF structure
    2. Computer vision (OpenCV) line detection on clean vector images
    3. Text-based underscore detection
    4. Intelligent correlation of lines with nearby text labels
    
    This mirrors the approach used by professional tools like macOS PDF viewers.
    """
    # Import time at module level to avoid context issues
    # start_time = time.time()
    
    try:
        doc = fitz.open(get_absolute_path(file_path))
        all_form_fields = []
        
        max_pages = min(len(doc), 100)

        for page_num, page in enumerate(doc[:max_pages]):
            if len(page.get_text()) < 50:
                continue

            vector_lines = extract_vector_lines_fast(page, page_num)
            text_underscore_rects = extract_text_underscores(page)
            
            all_field_rects = vector_lines + text_underscore_rects
            # Increase tolerance to merge fields that are close but not strictly overlapping.
            merged_rects = merge_overlapping_rects(all_field_rects, tolerance=10)
            
            # Define a standard height for all form fields
            STANDARD_FIELD_HEIGHT = 12  # in points

            for i, rect in enumerate(merged_rects):
                # Standardize the height of the rectangle around its vertical center
                original_center_y = (rect.y0 + rect.y1) / 2
                rect.y0 = original_center_y - (STANDARD_FIELD_HEIGHT / 2)
                rect.y1 = original_center_y + (STANDARD_FIELD_HEIGHT / 2)

                field_name = find_field_label(page, rect, page_num, i)
                
                if len(field_name) < 2 or "signature" in field_name.lower():
                    continue

                # IMPORTANT: This is the full, correct data structure for a field
                all_form_fields.append({
                    "field_name": field_name,
                    "field_type": "text",
                    "is_required": False,
                    "page_number": page_num + 1,
                    "coordinates": [ # The coordinates must be included here
                        {"x": rect.x0/page.rect.width, "y": rect.y0/page.rect.height},
                        {"x": rect.x1/page.rect.width, "y": rect.y0/page.rect.height},
                        {"x": rect.x1/page.rect.width, "y": rect.y1/page.rect.height},
                        {"x": rect.x0/page.rect.width, "y": rect.y1/page.rect.height}
                    ]
                })
        
        doc.close()
        
        if not all_form_fields:
            return '{"error": "No form fields were found using high-speed vector analysis."}'
        
        # --- THIS IS THE CORRECTED SECTION ---
        
        # 1. Define the full blueprint structure with ALL fields and coordinates
        full_blueprint_data = {
            "form_fields": all_form_fields, # Use the list that contains the coordinates
            "detection_method": "high_speed_vector_analysis",
            "total_fields": len(all_form_fields)
        }
        
        # 2. Save the complete blueprint data to the file
        temp_path = get_output_path("temp_local_blueprint", ".json")
        try:
            with open(temp_path, 'w') as f:
                json.dump(full_blueprint_data, f, indent=2)
            blueprint_path_for_adk = temp_path
        except Exception as e:
            print(f"Warning: Could not save blueprint file: {e}")
            blueprint_path_for_adk = None
        
        # 3. Create the simplified response for the ADK agent separately
        simplified_fields_for_adk = []
        for field in all_form_fields[:3]: # Limit to first 3 for display to prevent token limit issues
            simplified_fields_for_adk.append({
                "field_name": field["field_name"][:30],  # Also reduce field name length
                "page_number": field["page_number"]
            })
        
        # 4. Return the simplified list to the agent, but the file is saved with full data
        return json.dumps({
            "form_fields": simplified_fields_for_adk,
            "total_found": len(all_form_fields),
            "blueprint_saved_to": blueprint_path_for_adk
        })

    except Exception as e:
        return f'{{"error": "An error occurred in high-speed vector analysis: {type(e).__name__} - {str(e)}"}}'



def extract_vector_lines_fast(page: fitz.Page, page_num: int) -> list:
    """
    (REVISED) Extracts lines using a more robust two-pronged approach:
    1. Direct vector graphics analysis via page.get_drawings().
    2. A more sensitive OpenCV analysis on a higher-resolution rasterization of the page.
    This function now runs both methods to catch different types of lines.
    """
    line_rects = []

    # --- Method 1: Direct drawing analysis (Fast, for clean vector lines) ---
    try:
        drawings = page.get_drawings()
        for drawing in drawings:
            # This part of your original code is good, but we can relax the constraints slightly.
            for path in drawing.get("items", []):
                if path[0] == "l":  # Check for a line command
                    p1, p2 = path[1], path[2]
                    # Check for horizontal-ish lines
                    if abs(p1.y - p2.y) < 5 and abs(p1.x - p2.x) > 20: # Length > 20, height diff < 5
                        rect = fitz.Rect(p1, p2)
                        # Add a small vertical tolerance to the bounding box
                        rect.y0 -= 2
                        rect.y1 += 2
                        line_rects.append(rect)
    except Exception as e:
        # print(f"Warning: Could not process vector drawings on page {page_num}: {e}")
        pass # Continue to CV analysis
        # print(f"ERROR in {__name__}: {e}") # This will print any hidden errors

    # --- Method 2: Rasterization + OpenCV analysis (More robust for drawn/scanned lines) ---
    try:
        # Render page to a higher-quality image for better analysis
        dpi = 150  # Increased DPI for better line fidelity. Trade-off: uses more memory.
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
        
        # Safety check for very large images
        if pix.width * pix.height > 10_000_000: # Limit to 10 megapixels
            return line_rects

        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w)
        
        inverted_img = cv2.bitwise_not(img)
        
        # Use a less aggressive kernel to avoid deleting shorter lines.
        # This kernel will find horizontal lines of about 15px or longer.
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))
        morph = cv2.morphologyEx(inverted_img, cv2.MORPH_OPEN, kernel)
        
        # Loosen HoughLinesP parameters to catch more potential lines.
        # minLineLength is now shorter, maxLineGap is larger to connect dashed lines.
        lines = cv2.HoughLinesP(
            morph, 
            rho=1, 
            theta=np.pi / 180, 
            threshold=50, 
            minLineLength=30,  # Reduced from 50
            maxLineGap=15      # Increased from 5
        )
        
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                
                # Convert image coordinates back to PDF coordinates
                pdf_rect = fitz.Rect(x1, y1, x2, y2) / dpi * 72
                
                # Filter for horizontal lines again after detection
                if pdf_rect.height < 10 and pdf_rect.width > 20:
                    # Add vertical padding to ensure it can be merged and found
                    pdf_rect.y0 -= 3
                    pdf_rect.y1 += 3
                    line_rects.append(pdf_rect)

    except Exception as e:
        # print(f"Warning: OpenCV analysis failed on page {page_num}: {e}")
        # print(f"ERROR in {__name__}: {e}") # This will print any hidden errors
        pass
        
    return line_rects

def extract_text_underscores(page: fitz.Page) -> list:
    """
    (REVISED) Extracts underscore characters with improved accuracy.
    Uses `get_text("rawdict")` to get precise bounding boxes for each character,
    eliminating the guesswork of proportional fonts.
    """
    underscore_rects = []
    
    try:
        # "rawdict" provides character-level detail including precise bboxes
        blocks = page.get_text("rawdict").get("blocks", [])
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    for char in span.get("chars", []):
                        # Check if the character is an underscore
                        if char.get("c") == "_":
                            # Use the precise bounding box for this character
                            bbox = char.get("bbox")
                            if bbox:
                                underscore_rects.append(fitz.Rect(bbox))
    
    except Exception as e:
        # print(f"Warning: Could not extract text underscores: {e}")
        print(f"ERROR in {__name__}: {e}") # This will print any hidden errors
        # pass
        
    # After finding all individual underscore characters, we merge adjacent ones.
    # The main `merge_overlapping_rects` will handle this perfectly.
    return underscore_rects

def find_underscore_segments_in_text(text, bbox):
    """
    Analyze a text span to find individual underscore segments and their approximate positions.
    Returns a list of rectangles for each underscore segment.
    """
    segments = []
    
    try:
        # Find all continuous underscore sequences
        underscore_pattern = re.finditer(r'_{2,}', text)  # 2 or more consecutive underscores
        
        if not underscore_pattern:
            return segments
        
        # Calculate character width (approximate)
        text_width = bbox[2] - bbox[0]
        char_width = text_width / len(text) if len(text) > 0 else 10
        
        for match in re.finditer(r'_{2,}', text):
            start_pos = match.start()
            end_pos = match.end()
            underscore_text = match.group()
            
            # Calculate approximate position of this underscore segment
            segment_x0 = bbox[0] + (start_pos * char_width)
            segment_x1 = bbox[0] + (end_pos * char_width)
            
            # Ensure minimum width for form field
            if segment_x1 - segment_x0 < 20:
                segment_x1 = segment_x0 + 20
            
            segment_rect = fitz.Rect(segment_x0, bbox[1], segment_x1, bbox[3])
            segments.append(segment_rect)
    
    except Exception as e:
        print(f"ERROR in {__name__}: {e}") # This will print any hidden errors
        # pass  # Silently handle errors to prevent output overflow
    
    return segments

def find_field_label(page, rect, page_num, index):
    """
    (REVISED) Intelligent field label detection that prioritizes finding any valid
    label but reliably falls back to a generic name if no suitable label is found.
    """
    try:
        # Search areas: prioritize closer areas to this specific field
        search_areas = [
            # Primary: Immediately to the left of the field
            fitz.Rect(max(0, rect.x0 - 200), rect.y0 - 10, rect.x0 - 3, rect.y1 + 10),
            # Secondary: Directly above the field 
            fitz.Rect(rect.x0 - 10, max(0, rect.y0 - 30), rect.x1 + 10, rect.y0 - 2),
        ]
        
        candidate_words = []
        
        # Get all words on the page once to avoid repeated calls
        all_words = page.get_text("words")
        
        # Common non-label words to filter out
        stop_words = {'the', 'and', 'or', 'of', 'to', 'in', 'for', 'on', 'at', 'a', 'an', 'no', 'is', 'are', 'was', 'were'}

        for area in search_areas:
            # Filter words that are inside our search area
            words_in_area = [w for w in all_words if fitz.Rect(w[:4]).intersects(area)]
            
            for word in words_in_area:
                x0, y0, x1, y1, text = word[:5]
                text_clean = text.strip()
                
                # Basic filtering for relevance
                if len(text_clean) > 1 and not text_clean.isdigit() and text_clean.lower() not in stop_words:
                    candidate_words.append(word)

        if not candidate_words:
            # If no words are found nearby, immediately return a generic label
            return f"Field_{page_num + 1}_{index + 1}"

        # Sort candidates primarily by vertical alignment, then by horizontal position (right-to-left)
        field_v_center = (rect.y0 + rect.y1) / 2
        candidate_words.sort(key=lambda w: (abs((w[1] + w[3]) / 2 - field_v_center), -w[2])) # sort by vertical proximity, then reverse horizontal

        # Build the label from the best candidates (up to 4 words)
        label_words = [w[4] for w in candidate_words[:4]]
        
        # The words are sorted right-to-left, so we reverse them to get natural reading order
        label_words.reverse()
        
        best_label = " ".join(label_words)
        
        # Clean up the final label
        best_label = re.sub(r'[^a-zA-Z0-9\s]', '', best_label).strip() # Remove punctuation
        best_label = re.sub(r'\s+', ' ', best_label) # Consolidate whitespace

        # If after all that, the label is empty or too short, fall back to generic.
        if len(best_label) < 2:
            return f"Field_{page_num + 1}_{index + 1}"
        
        return best_label[:50]  # Return the found label, truncated to 50 chars

    except Exception as e:
        # If any error occurs, always return a generic name
        # print(f"Error in find_field_label: {e}") # You can uncomment for debugging
        return f"Field_{page_num + 1}_{index + 1}"

# ============================================
# PDF Manipulation & Blueprint Tools
# ============================================

def list_pdf_form_fields(pdf_path: str) -> str:
    """Inspects a PDF file and returns a JSON list of its fillable form field names."""
    try:
        doc = fitz.open(get_absolute_path(pdf_path))
        fields = [field.field_name for page in doc for field in page.widgets() if field.field_name]
        if not fields:
            return '{"fields": [], "message": "No existing interactive form fields were found."}'
        return json.dumps({"fields": fields, "message": f"Found {len(fields)} existing fields."})
    except Exception as e:
        return f'{{"error": "An error occurred while processing the PDF: {str(e)}"}}'


def create_fields_from_blueprint(pdf_path: str, json_blueprint_path: str) -> str:
    """(DEBUG VERSION) Adds empty form fields to a PDF based on a JSON blueprint file."""
    print("\n--- [DEBUG] Starting create_fields_from_blueprint ---")
    try:
        absolute_pdf_path = get_absolute_path(pdf_path)
        print(f"[DEBUG] Absolute PDF Path: {absolute_pdf_path}")

        # --- Step 1: Locate the Blueprint ---
        if json_blueprint_path is None:
            json_blueprint_path = get_output_path("temp_local_blueprint", ".json")
            print(f"[DEBUG] Blueprint path not provided, using temporary path: {json_blueprint_path}")
        
        if not os.path.exists(json_blueprint_path):
            error_msg = "FATAL: Blueprint file not found at the specified path."
            print(f"[DEBUG] {error_msg}")
            return json.dumps({"error": error_msg, "path_checked": json_blueprint_path})
        
        print(f"[DEBUG] Found blueprint file. Loading from: {json_blueprint_path}")
        with open(get_absolute_path(json_blueprint_path), 'r') as f:
            blueprint = json.load(f)

        # --- Step 2: Load PDF and Process Fields ---
        doc = fitz.open(absolute_pdf_path)
        print(f"[DEBUG] Successfully opened PDF with {len(doc)} pages.")
        
        form_fields_to_process = blueprint.get("form_fields", [])
        total_fields = len(form_fields_to_process)
        if total_fields == 0:
            print("[DEBUG] WARNING: The blueprint contains 0 form fields. Nothing to create.")
        else:
            print(f"[DEBUG] Found {total_fields} fields in blueprint to process.")

        used_field_names = set()
        fields_added_count = 0

        # --- Step 3: Loop Through Each Field in Blueprint ---
        for i, field in enumerate(form_fields_to_process):
            original_name = field.get("field_name", f"unnamed_field_{i}")
            print(f"\n[DEBUG] Processing Field {i+1}/{total_fields}: '{original_name}'")

            # VALIDATION 1: Page Number
            page_num_one_based = field.get("page_number")
            if not isinstance(page_num_one_based, int) or not (1 <= page_num_one_based <= len(doc)):
                print(f"  -> [SKIP] Invalid or missing page number: {page_num_one_based}")
                continue
            
            page = doc[page_num_one_based - 1]

            # VALIDATION 2: Coordinates
            coords = field.get("coordinates")
            if not (isinstance(coords, list) and len(coords) == 4):
                print(f"  -> [SKIP] Coordinates are not a list of 4 points. Value: {coords}")
                continue

            try:
                # These calculations will fail if coords are not in the expected [{x,y},...] format
                x0 = coords[0]['x'] * page.rect.width
                y0 = coords[0]['y'] * page.rect.height
                x1 = coords[2]['x'] * page.rect.width
                y1 = coords[2]['y'] * page.rect.height
            except (TypeError, KeyError, IndexError) as e:
                print(f"  -> [SKIP] Malformed coordinate structure. Error: {e}. Coords: {coords}")
                continue

            # Add a vertical offset to prevent obscuring the baseline (e.g., semi-colons)
            VERTICAL_OFFSET_PERCENTAGE = 0.005  # 0.5% of page height
            vertical_offset = page.rect.height * VERTICAL_OFFSET_PERCENTAGE
            y0 -= vertical_offset
            y1 -= vertical_offset
            
            # VALIDATION 3: Rectangle Dimensions
            if x1 <= x0 or y1 <= y0:
                print(f"  -> [SKIP] Invalid rectangle dimensions (x1 <= x0 or y1 <= y0). Coords: ({x0}, {y0}, {x1}, {y1})")
                continue

            # If all validations pass, create the widget
            # (Your sanitization logic is good, keeping it as is)
            sanitized_name = re.sub(r'[^a-zA-Z0-9_]', '', original_name.replace(' ', '_'))[:50]
            unique_name = sanitized_name
            counter = 1
            while unique_name in used_field_names:
                unique_name = f"{sanitized_name}_{counter}"
                counter += 1
            used_field_names.add(unique_name)

            rect = fitz.Rect(x0, y0, x1, y1)
            widget = fitz.Widget()
            widget.rect = rect
            widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            widget.field_name = unique_name
            widget.field_value = ""
            
            page.add_widget(widget)
            fields_added_count += 1
            print(f"  -> [SUCCESS] Added widget '{unique_name}' to page {page_num_one_based}.")

        # --- Step 4: Save the Final Document ---
        print(f"\n[DEBUG] Finished processing. Total fields added: {fields_added_count}/{total_fields}")
        if fields_added_count > 0:
            output_path = get_output_path(pdf_path, "_fields_created")
            print(f"[DEBUG] Saving final PDF to: {output_path}")
            doc.save(output_path, garbage=4, deflate=True, clean=True)
            doc.close()
            return json.dumps({"success": True, "path": output_path, "fields_added": fields_added_count})
        else:
            doc.close()
            print("[DEBUG] No fields were added, so no output file was saved.")
            return json.dumps({"error": "No new fields were added to the PDF.", "fields_added": 0})

    except Exception as e:
        tb_str = traceback.format_exc()
        error_message = f"An error occurred during field creation: {type(e).__name__} - {str(e)}\nTraceback:\n{tb_str}"
        print(f"[DEBUG] {error_message}")
        return json.dumps({"error": error_message})

# def create_fields_from_blueprint(pdf_path: str, json_blueprint_path: str) -> str:
#     """Adds empty form fields to a PDF based on a JSON blueprint file.
#     If json_blueprint_path is None, attempts to load from temp_local_blueprint.json."""
#     try:
#         absolute_pdf_path = get_absolute_path(pdf_path)
        
#         # If no blueprint path provided, try to load from temp file
#         if json_blueprint_path is None:
#             temp_path = get_output_path("temp_local_blueprint", ".json")
#             if not os.path.exists(temp_path):
#                 return '{"error": "No blueprint file provided and no temporary blueprint found. Please run field detection first."}'
#             json_blueprint_path = temp_path
        
#         with open(get_absolute_path(json_blueprint_path), 'r') as f:
#             blueprint = json.load(f)

#         doc = fitz.open(absolute_pdf_path)
        
#         # Keep track of sanitized names to ensure uniqueness
#         used_field_names = set()

#         def sanitize_field_name(name: str) -> str:
#             # Remove invalid characters, replace spaces with underscores
#             name = re.sub(r'[^a-zA-Z0-9_]', '', name.replace(' ', '_'))
#             # Truncate to a reasonable length
#             return name[:50]

#         for field in blueprint.get("form_fields", []):
#             page_num_one_based = field.get("page_number", 1)
#             if not (1 <= page_num_one_based <= len(doc)):
#                 print(f"[DEBUG-PDF] Skipping field '{field.get('field_name')}' due to invalid page number: {page_num_one_based}.")
#                 continue
            
#             page = doc[page_num_one_based - 1]
#             coords = field.get("coordinates", [])

#             if not (isinstance(coords, list) and len(coords) == 4 and
#                     all(isinstance(p, dict) and 'x' in p and 'y' in p and
#                         isinstance(p['x'], (int, float)) and isinstance(p['y'], (int, float))
#                         for p in coords)):
#                 print(f"[DEBUG-PDF] Skipping field '{field.get('field_name')}' due to invalid or malformed coordinates.")
#                 continue

#             original_name = field.get("field_name", "unnamed")
#             sanitized_name = sanitize_field_name(original_name)
            
#             # Ensure the field name is unique
#             unique_name = sanitized_name
#             counter = 1
#             while unique_name in used_field_names:
#                 unique_name = f"{sanitized_name}_{counter}"
#                 counter += 1
#             used_field_names.add(unique_name)

#             x0 = coords[0]['x'] * page.rect.width
#             y0 = coords[0]['y'] * page.rect.height
#             x1 = coords[2]['x'] * page.rect.width
#             y1 = coords[2]['y'] * page.rect.height

#             # Also validate the rectangle dimensions themselves to prevent errors
#             if x1 <= x0 or y1 <= y0:
#                 print(f"[DEBUG-PDF] Skipping field '{unique_name}' due to invalid rectangle dimensions (x1 <= x0 or y1 <= y0). Coords: ({x0}, {y0}, {x1}, {y1})")
#                 continue

#             rect = fitz.Rect(x0, y0, x1, y1)
            
#             # Create widget by setting attributes for compatibility with older PyMuPDF.
#             widget = fitz.Widget()
#             widget.rect = rect
#             widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
#             widget.field_name = unique_name
#             widget.field_value = ""
            
#             page.add_widget(widget)
        
#         output_path = get_output_path(pdf_path, "_fields_created")
#         doc.save(output_path, garbage=4, deflate=True, clean=True)
#         doc.close()
        
#         # Return the path AND the list of actual field names created
#         return json.dumps({
#             "success": True, 
#             "path": output_path,
#             "created_fields": list(used_field_names)
#         })
    
#     except Exception as e:
#         tb_str = traceback.format_exc()
#         error_message = f"An error occurred during field creation: {type(e).__name__} - {str(e)}\nTraceback:\n{tb_str}"
#         print(f"[DEBUG-PDF] {error_message}")
#         return json.dumps({"error": error_message})


def fill_form_fields(pdf_path: str, user_data_json: str) -> str:
    """Fills the existing form fields of a PDF with user data from a JSON string."""
    try:
        user_data = json.loads(user_data_json)
        doc = fitz.open(get_absolute_path(pdf_path))
        for page in doc:
            for field in page.widgets():
                if field.field_name in user_data:
                    field.field_value = str(user_data[field.field_name])
                    field.update()
        
        output_path = get_output_path(pdf_path, "_filled", clean_base_name=True)
        doc.save(output_path, garbage=4, deflate=True, clean=True)
        return f'{{"success": true, "path": "{output_path}"}}'
    except Exception as e:
        return f'{{"error": "An error occurred: {type(e).__name__} - {str(e)}"}}'

# ============================================
# Utility & Debugging Tools
# ============================================

def save_json_to_file(json_data: str, output_filename: str) -> str:
    """Saves a JSON string to a file in the output directory."""
    try:
        output_path = get_output_path(output_filename, "", new_extension='json')
        with open(output_path, 'w') as f:
            # First, validate if json_data is a string that can be loaded into a dict
            data_dict = json.loads(json_data)
            json.dump(data_dict, f, indent=2)
        return f'{{"success": true, "path": "{output_path}"}}'
    except json.JSONDecodeError:
        return '{"error": "Input string is not valid JSON."}'
    except Exception as e:
        return f'{{"error": "Failed to save file: {str(e)}"}}'

def check_configuration() -> str:
    """Checks and returns the loaded configuration for Azure Document AI."""
    try:
        config = load_config()
        return json.dumps({k: config.get(k, 'Not Set') for k in [
            'AZURE_DOC_INTEL_ENDPOINT', 'AZURE_DOC_INTEL_KEY'
        ]}, indent=2)
    except Exception as e:
        return f"An error occurred while checking configuration: {str(e)}"
    
def debug_and_visualize_fields(file_path: str, page_num: int):
    """
    A debugging utility to visualize the output of the detection functions.
    It saves an image of the page with detected rectangles drawn on it.
    """
    print("="*50)
    print(f"STARTING DEBUG FOR: {file_path}, PAGE: {page_num}")
    print("="*50)

    try:
        doc = fitz.open(get_absolute_path(file_path))
        if page_num >= len(doc):
            print(f"Error: Invalid page number. Document only has {len(doc)} pages.")
            return

        page = doc[page_num]

        # --- Run Detection Functions ---
        # 1. Vector and OpenCV-based lines
        vector_cv_rects = extract_vector_lines_fast(page, page_num)
        print(f"[INFO] Found {len(vector_cv_rects)} potential lines using vector/OpenCV analysis.")

        # 2. Text-based underscores
        text_underscore_rects = extract_text_underscores(page)
        print(f"[INFO] Found {len(text_underscore_rects)} potential lines using text underscore analysis.")

        # --- Visualize the Detections ---
        # Get an image of the page
        pix = page.get_pixmap(dpi=150)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        
        # OpenCV expects BGR, PyMuPDF gives RGB or GRAY. Convert if necessary.
        if img.shape[2] == 3: # RGB
             img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elif img.shape[2] == 1: # GRAY
             img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

        # Draw rectangles from vector/CV analysis in RED
        for rect in vector_cv_rects:
            # Convert PDF rect coordinates to image pixel coordinates
            img_rect = rect * (150/72) 
            p1 = (int(img_rect.x0), int(img_rect.y0))
            p2 = (int(img_rect.x1), int(img_rect.y1))
            cv2.rectangle(img, p1, p2, (0, 0, 255), 2) # Red color in BGR

        # Draw rectangles from text analysis in BLUE
        for rect in text_underscore_rects:
            # Convert PDF rect coordinates to image pixel coordinates
            img_rect = rect * (150/72)
            p1 = (int(img_rect.x0), int(img_rect.y0))
            p2 = (int(img_rect.x1), int(img_rect.y1))
            cv2.rectangle(img, p1, p2, (255, 0, 0), 2) # Blue color in BGR
            
        # Merge all detected rectangles for a final "green" overlay
        all_rects = vector_cv_rects + text_underscore_rects
        merged_rects = merge_overlapping_rects(all_rects, tolerance=5) # Assuming you have this function
        print(f"[INFO] After merging, resulted in {len(merged_rects)} final field areas.")
        
        for rect in merged_rects:
            img_rect = rect * (150/72)
            p1 = (int(img_rect.x0), int(img_rect.y0))
            p2 = (int(img_rect.x1), int(img_rect.y1))
            cv2.rectangle(img, p1, p2, (0, 255, 0), 1) # Green outline for merged

        # Save the output image
        output_filename = f"debug_output_page_{page_num}.png"
        cv2.imwrite(output_filename, img)
        print(f"\n[SUCCESS] Debug image saved to: {output_filename}")
        print("Please check this image. Red boxes are from vector/CV, Blue are from text, Green are the final merged fields.")

        doc.close()

    except Exception as e:
        print(f"An error occurred during debugging: {e}")

def get_tools():
    """Returns the list of tools for the agent."""
    return [
        list_pdf_form_fields,
        create_form_field_blueprint_from_azure,
        create_underscore_blueprint_from_azure,  # Azure-based underscore detection (handles drawn lines)
        extract_underscore_fields,  # Local underscore detection method
        extract_fields_with_local_heuristics,
        save_json_to_file,
        create_fields_from_blueprint,
        fill_form_fields,
        check_configuration,
        debug_and_visualize_fields,
    ]
