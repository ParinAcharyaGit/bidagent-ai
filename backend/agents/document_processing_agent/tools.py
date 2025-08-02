import os
import json
import re
import traceback
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
    import time
    start_time = time.time()
    
    try:
        print(f"Starting local analysis...")
        
        doc = fitz.open(get_absolute_path(file_path))
        all_form_fields = []
        
        # Limit processing to first 3 pages to prevent hanging
        max_pages = min(len(doc), 3)
        print(f"Processing {max_pages} pages...")

        for page_num, page in enumerate(doc[:max_pages]):
            print(f"Page {page_num + 1}/{max_pages}...")
            
            if len(page.get_text()) < 50:
                continue

            # Step 1: Vector Graphics Analysis
            vector_lines = extract_vector_lines_fast(page, page_num)
            
            # Step 2: Text-Based Underscore Detection
            text_underscore_rects = extract_text_underscores(page)
            
            # Step 3: Combine detected areas
            all_field_rects = vector_lines + text_underscore_rects
            merged_rects = merge_overlapping_rects(all_field_rects, tolerance=3)
            
            # Step 4: Find labels and create form fields
            for i, rect in enumerate(merged_rects):
                field_name = find_field_label(page, rect, page_num, i)
                
                # Skip common non-fields
                if len(field_name) < 2 or "signature" in field_name.lower():
                    continue

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
                    "detection_method": "high_speed_vector_analysis"
                })
        
        if not all_form_fields:
            return '{"error": "No form fields were found using high-speed vector analysis."}'
        
        total_time = time.time() - start_time
        print(f"Analysis complete. Found {len(all_form_fields)} fields in {total_time:.1f}s")
        
        return json.dumps({
            "form_fields": all_form_fields, 
            "detection_method": "high_speed_vector_analysis",
            "total_fields": len(all_form_fields),
            "processing_time_seconds": round(total_time, 2)
        }, indent=2)

    except Exception as e:
        return f'{{"error": "An error occurred in high-speed vector analysis: {type(e).__name__} - {str(e)}"}}'

def extract_vector_lines_fast(page, page_num):
    """
    High-speed vector graphics extraction using PyMuPDF's drawing analysis.
    This mimics professional PDF tools by analyzing the actual vector graphics structure.
    """
    import time
    
    try:
        # Method 1: Direct drawing analysis (fastest)
        drawings = page.get_drawings()
        line_rects = []
        
        for drawing in drawings:
            # Handle different drawing object structures
            if isinstance(drawing, dict):
                items = drawing.get("items", [])
            else:
                # For tuple/other formats, try to access as a sequence
                try:
                    items = drawing[1] if len(drawing) > 1 else []
                except (TypeError, IndexError):
                    items = []
            
            for path in items:
                if isinstance(path, dict) and path.get("type") == "l":  # Line type
                    points = path.get("points", [])
                    if len(points) >= 2:
                        # Check if it's a horizontal line suitable for form field
                        start_point = points[0]
                        end_point = points[-1]
                        
                        x0, y0 = start_point
                        x1, y1 = end_point
                        
                        # Only consider horizontal lines with reasonable length
                        line_width = abs(x1 - x0)
                        line_height = abs(y1 - y0)
                        
                        if line_width > 30 and line_height < 5 and line_width > line_height * 3:
                            # Create a bounding rectangle for the line
                            rect = fitz.Rect(min(x0, x1), min(y0, y1) - 2, max(x0, x1), max(y0, y1) + 2)
                            line_rects.append(rect)
        
        # Method 2: Rasterization + OpenCV analysis (fallback for complex graphics)
        if len(line_rects) < 3:  # If we didn't find many lines, try OpenCV method            
            # Render page to image for computer vision analysis
            dpi = 120  # Further reduced DPI for better performance
            pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
            img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w)
            
            # Invert image for line detection (lines become white on black background)
            inverted_img = cv2.bitwise_not(img_data)
            
            # Apply morphological operations to enhance line detection
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 1))
            morph = cv2.morphologyEx(inverted_img, cv2.MORPH_OPEN, kernel)
            
            # Detect lines using HoughLinesP
            lines = cv2.HoughLinesP(morph, rho=1, theta=np.pi/180, threshold=30, minLineLength=30, maxLineGap=3)  # More lenient parameters
            
            if lines is not None:
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    
                    # Convert back from image coordinates to PDF coordinates
                    pdf_x1 = (x1 / pix.w) * page.rect.width
                    pdf_y1 = (y1 / pix.h) * page.rect.height
                    pdf_x2 = (x2 / pix.w) * page.rect.width
                    pdf_y2 = (y2 / pix.h) * page.rect.height
                    
                    # Filter for horizontal lines
                    line_width = abs(pdf_x2 - pdf_x1)
                    line_height = abs(pdf_y2 - pdf_y1)
                    
                    if line_width > 30 and line_height < 10 and line_width > line_height * 2:
                        rect = fitz.Rect(min(pdf_x1, pdf_x2), min(pdf_y1, pdf_y2) - 3, 
                                       max(pdf_x1, pdf_x2), max(pdf_y1, pdf_y2) + 3)
                        line_rects.append(rect)
        
        return line_rects
    
    except Exception as e:
        return []

def extract_text_underscores(page):
    """
    Extract individual underscore segments directly from text using PyMuPDF's text analysis.
    This finds actual underscore characters and creates separate fields for each segment.
    """
    try:
        underscore_rects = []
        
        # Method 1: Character-level analysis to find individual underscore segments
        text_blocks = page.get_text("dict")
        for block in text_blocks.get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        bbox = span.get("bbox")
                        
                        if bbox and "_" in text:
                            # Find all underscore segments in this span
                            underscore_segments = find_underscore_segments_in_text(text, bbox)
                            underscore_rects.extend(underscore_segments)
        
        # Method 2: Word-level analysis for backup detection
        words = page.get_text("words")
        
        for word in words:
            x0, y0, x1, y1, text = word[:5]
            
            # Look for words that are primarily underscores
            if "_" in text:
                underscore_count = text.count("_")
                total_chars = len(text)
                
                # Consider it an underscore field if >70% of characters are underscores
                # or if it's a long sequence of underscores
                if (underscore_count / total_chars > 0.7) or (underscore_count >= 5):
                    rect = fitz.Rect(x0, y0, x1, y1)
                    
                    # Check if this overlaps with existing segments (avoid duplicates)
                    is_duplicate = any(rect.intersects(existing) for existing in underscore_rects)
                    if not is_duplicate:
                        underscore_rects.append(rect)
        
        # Sort by position (top to bottom, left to right)
        underscore_rects.sort(key=lambda r: (r.y0, r.x0))
        
        return underscore_rects
    
    except Exception as e:
        return []

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
        print(f"[DEBUG-VECTOR] Error analyzing underscore segments: {e}")
    
    return segments

def find_field_label(page, rect, page_num, index):
    """
    Intelligent field label detection using spatial analysis.
    Looks for text labels positioned logically relative to form fields.
    Optimized for individual underscore segments.
    """
    try:
        # Calculate field center for distance-based scoring
        field_center_x = (rect.x0 + rect.x1) / 2
        field_center_y = (rect.y0 + rect.y1) / 2
        
        # Search areas: prioritize closer areas to this specific field
        search_areas = [
            # Primary: Immediately to the left of the field (narrow search)
            fitz.Rect(max(0, rect.x0 - 150), rect.y0 - 5, rect.x0 - 2, rect.y1 + 5),
            # Secondary: Slightly above the field 
            fitz.Rect(rect.x0 - 30, max(0, rect.y0 - 20), rect.x1 + 30, rect.y0 - 1),
            # Tertiary: Broader left search for longer labels
            fitz.Rect(max(0, rect.x0 - 300), rect.y0 - 15, rect.x0 - 5, rect.y1 + 15)
        ]
        
        best_label = ""
        best_score = 0
        
        for area_idx, search_area in enumerate(search_areas):
            # Get words in the search area
            words = page.get_text("words", clip=search_area)
            
            if words:
                # Filter and score words based on proximity and relevance
                candidate_words = []
                
                for word in words:
                    x0, y0, x1, y1, text = word[:5]
                    word_center_x = (x0 + x1) / 2
                    word_center_y = (y0 + y1) / 2
                    
                    # Skip very short words, numbers only, underscore-heavy words, or common non-label words
                    text_clean = text.strip()
                    underscore_ratio = text_clean.count('_') / len(text_clean) if len(text_clean) > 0 else 0
                    
                    if (len(text_clean) >= 2 and 
                        not text_clean.isdigit() and 
                        underscore_ratio < 0.5 and  # Skip words that are mostly underscores
                        text_clean.lower() not in ['the', 'and', 'or', 'of', 'to', 'in', 'for', 'on', 'at', 'a', 'an', 'no', 'no.']):
                        
                        # Calculate distance from word to field
                        distance = ((word_center_x - field_center_x) ** 2 + (word_center_y - field_center_y) ** 2) ** 0.5
                        candidate_words.append((text_clean, distance, word_center_y, word_center_x))
                
                if candidate_words:
                    # Sort by distance (closer words first), then by position
                    candidate_words.sort(key=lambda w: (w[1], w[2], w[3]))
                    
                    # Build label from closest relevant words (limit to prevent overly long labels)
                    label_words = [w[0] for w in candidate_words[:3]]  # Max 3 words for precision
                    
                    # Remove duplicate words while preserving order
                    seen = set()
                    unique_words = []
                    for word in label_words:
                        word_lower = word.lower()
                        if word_lower not in seen:
                            unique_words.append(word)
                            seen.add(word_lower)
                    
                    candidate_label = " ".join(unique_words).strip(": \n\t")
                    candidate_label = re.sub(r'\s+', ' ', candidate_label)
                    
                    # Score the label based on quality indicators
                    score = 0
                    
                    # Prefer labels that end with colon
                    if candidate_label.endswith(':'):
                        score += 15
                        candidate_label = candidate_label[:-1].strip()
                    
                    # Prefer labels with field-like keywords
                    field_keywords = ['name', 'address', 'phone', 'email', 'date', 'number', 
                                    'company', 'title', 'license', 'amount', 'total', 'description',
                                    'bid', 'contractor', 'contact', 'signature', 'type', 'code', 'id']
                    
                    keyword_matches = sum(1 for keyword in field_keywords if keyword in candidate_label.lower())
                    score += keyword_matches * 8
                    
                    # Prefer labels from closer search areas (more precise)
                    if area_idx == 0:  # Immediate left
                        score += 10
                    elif area_idx == 1:  # Above
                        score += 5
                    
                    # Prefer shorter, more concise labels
                    if len(candidate_label) <= 15:
                        score += 5
                    elif len(candidate_label) <= 25:
                        score += 2
                    
                    # Penalize very long labels or generic text
                    if (len(candidate_label) > 40 or 
                        any(word in candidate_label.lower() for word in ['page', 'form', 'document', 'section', 'instructions'])):
                        score -= 10
                    
                    # Bonus for proximity (closer words get higher scores)
                    if candidate_words and candidate_words[0][1] < 50:  # Very close
                        score += 5
                    elif candidate_words and candidate_words[0][1] < 100:  # Reasonably close
                        score += 2
                    
                    if score > best_score:
                        best_score = score
                        best_label = candidate_label
        
        # Clean up the best label
        if best_label and best_score > 0:
            best_label = re.sub(r'[^a-zA-Z0-9\s\-_().,]', '', best_label).strip()
            best_label = best_label[:40]  # Reasonable length limit
            
            if len(best_label) >= 2:
                return best_label
        
        # Fallback to generic name
        return f"Field_{page_num + 1}_{index + 1}"
    
    except Exception as e:
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
    """Adds empty form fields to a PDF based on a JSON blueprint file."""
    try:
        absolute_pdf_path = get_absolute_path(pdf_path)
        with open(get_absolute_path(json_blueprint_path), 'r') as f:
            blueprint = json.load(f)

        doc = fitz.open(absolute_pdf_path)
        
        # Keep track of sanitized names to ensure uniqueness
        used_field_names = set()

        def sanitize_field_name(name: str) -> str:
            # Remove invalid characters, replace spaces with underscores
            name = re.sub(r'[^a-zA-Z0-9_]', '', name.replace(' ', '_'))
            # Truncate to a reasonable length
            return name[:50]

        for field in blueprint.get("form_fields", []):
            page_num_one_based = field.get("page_number", 1)
            if not (1 <= page_num_one_based <= len(doc)):
                print(f"[DEBUG-PDF] Skipping field '{field.get('field_name')}' due to invalid page number: {page_num_one_based}.")
                continue
            
            page = doc[page_num_one_based - 1]
            coords = field.get("coordinates", [])

            if not (isinstance(coords, list) and len(coords) == 4 and
                    all(isinstance(p, dict) and 'x' in p and 'y' in p and
                        isinstance(p['x'], (int, float)) and isinstance(p['y'], (int, float))
                        for p in coords)):
                print(f"[DEBUG-PDF] Skipping field '{field.get('field_name')}' due to invalid or malformed coordinates.")
                continue

            original_name = field.get("field_name", "unnamed")
            sanitized_name = sanitize_field_name(original_name)
            
            # Ensure the field name is unique
            unique_name = sanitized_name
            counter = 1
            while unique_name in used_field_names:
                unique_name = f"{sanitized_name}_{counter}"
                counter += 1
            used_field_names.add(unique_name)

            x0 = coords[0]['x'] * page.rect.width
            y0 = coords[0]['y'] * page.rect.height
            x1 = coords[2]['x'] * page.rect.width
            y1 = coords[2]['y'] * page.rect.height

            # Also validate the rectangle dimensions themselves to prevent errors
            if x1 <= x0 or y1 <= y0:
                print(f"[DEBUG-PDF] Skipping field '{unique_name}' due to invalid rectangle dimensions (x1 <= x0 or y1 <= y0). Coords: ({x0}, {y0}, {x1}, {y1})")
                continue

            rect = fitz.Rect(x0, y0, x1, y1)
            
            # Create widget by setting attributes for compatibility with older PyMuPDF.
            widget = fitz.Widget()
            widget.rect = rect
            widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            widget.field_name = unique_name
            widget.field_value = ""
            
            page.add_widget(widget)
        
        output_path = get_output_path(pdf_path, "_fields_created")
        doc.save(output_path, garbage=4, deflate=True, clean=True)
        return f'{{"success": true, "path": "{output_path}"}}'
    except Exception as e:
        tb_str = traceback.format_exc()
        error_message = f"An error occurred during field creation: {type(e).__name__} - {str(e)}\nTraceback:\n{tb_str}"
        print(f"[DEBUG-PDF] {error_message}")
        return json.dumps({"error": error_message})

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
    ]
