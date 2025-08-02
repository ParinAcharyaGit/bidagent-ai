# Update 11: Automatic Underscore-Based Form Field Detection

## Objective
Develop a robust backend solution for detecting form fields based on underscore lines in PDFs, mirroring macOS's behavior.

## Challenges Identified
- Azure Document Intelligence tends to clean or normalize text, removing underscores.
- Local detection methods can succeed but require performance optimization.

## Proposed Solution Steps

### Step 1: Update PDF Analysis Tools
- **File:** `backend/requirements.txt`
  - **Action:** Ensure `opencv-python-headless` and `numpy` are included for high-performance image processing.

### Step 2: Implement High-Speed Vector Analysis
- **File:** `backend/agents/document_automation_manager/tools.py`
  - **Change:** Refactor this file to:
    - Use `PyMuPDF` to extract vector graphics as a clean image.
    - Apply `opencv-python-headless` to detect horizontal lines quickly.
    - Correlate detected lines with text to identify labels and form fields.

### Step 3: Update Local Heuristics Method
- Rewrite the `extract_fields_with_local_heuristics` function to:
  - Consolidate both vector graphic analysis and text detection.
  - Merge these results to produce a comprehensive list of form fields.

### Step 4: Simplify Agent Workflow
- **Files:** `backend/agents/document_automation_manager/agent.py`, `prompt.py`
  - **Action:** Update agent logic to solely rely on improved local detection for underscore-based form fields, removing fallback to less reliable cloud methods.

## Expected Outcome
- Achieve high accuracy and performance in detecting underscore-based form fields.
- Enhance user experience by ensuring fields are found reliably and efficiently.

# Update 10: The Azure Migration

## 1. Objective
To transition the entire document analysis and field identification workflow from Google Cloud Document AI to Azure Document Intelligence. This migration is driven by the need for a more robust, scalable, and secure solution that can more accurately identify potential form field locations on any given document.

## 2. Analysis of the Problem
Our previous solution using Google's Document AI services proved unable to consistently identify all the form fields we required. Furthermore, the user has requested we use Azure as it is more scalable and better for handling sensitive information. The multi-agent "Triumvirate" system we built for Google was also complex. Azure's capabilities allow for a significant simplification.

## 3. Proposed Solution - Step-by-Step

### Step 1: Update Environment
-   **File:** `backend/requirements.txt`
    -   **Action:** Add `azure-ai-documentintelligence` and `azure-identity`.
-   **File:** `backend/config.py`
    -   **Action:** Add new configuration variables for Azure credentials: `AZURE_DOC_INTEL_ENDPOINT = ""` and `AZURE_DOC_INTEL_KEY = ""`.

### Step 2: Architect the New Azure-based Agent System
-   **Action: Retire Old Agents.** Delete the directories for the Google-specific agents:
    -   `backend/agents/document_automation_manager/sub_agents/docai_tool_agent/`
    -   `backend/agents/document_automation_manager/sub_agents/ocr_tool_agent/`

-   **Action: Create the `azure_tool_agent`**.
    -   **Location:** `backend/agents/document_automation_manager/sub_agents/azure_tool_agent/`
    -   **`tools.py`**: This file will contain a single, powerful tool, `analyze_document_layout`.
        -   This tool will initialize the `DocumentIntelligenceClient` using the new credentials from `config.py`.
        -   It will take a file path as input and use the `"prebuilt-layout"` model to analyze the document.
        -   It will iterate through the `AnalyzeResult` to extract all words, their content, and their bounding box polygons (`word.polygon`).
        -   It will return a structured JSON object containing a list of all words with their coordinates.
    -   **`agent.py`**: This will define the `azure_tool_agent`, equipping it with the `analyze_document_layout` tool. Its prompt will be simple, focused on executing the tool when asked.

### Step 3: Update the Manager and Formatter Agents
-   **File:** `backend/agents/document_automation_manager/agent.py`
    -   **Action:** Modify the `document_automation_manager`.
    -   Remove the old `docai_tool_agent` and `ocr_tool_agent` from its `sub_agents` list.
    -   Add the new `azure_tool_agent` to its `sub_agents` list.
-   **File:** `backend/agents/document_automation_manager/prompt.py`
    -   **Action:** Update the `AUTOMATION_MANAGER_PROMPT`. The manager's logic will be simplified. It will no longer need to decide between multiple tool agents. Its primary role will be to receive the user's file, pass it to the `azure_tool_agent` for layout analysis, and then pass the resulting coordinate data to the `json_formatter_agent` for the final blueprint creation.

-   **File:** `backend/agents/document_automation_manager/sub_agents/json_formatter_agent/prompt.py`
    -   **Action:** Update the formatter's prompt to understand the new input data structure coming from the `azure_tool_agent`. It will continue to be responsible for the high-level reasoning of identifying field labels (e.g., "Company Name:") and determining the correct coordinates for placing a new input field based on the Azure tool's output.

## 4. Expected Outcome
-   A fully functional document analysis pipeline powered by Azure Document Intelligence.
-   A simpler and more maintainable agent architecture.
-   The system will be able to take any PDF, analyze its layout to find the coordinates of all text, and then generate a JSON blueprint identifying where new form fields should be created.
-   All dependencies on Google's Document AI will be removed from the project.

# Update 2: Intelligent Search Query Enhancement

## 1. Objective
To empower the `bid_search_agent` to intelligently expand and refine a user's search query. Instead of using the user's exact words, the agent will leverage its LLM capabilities to generate better search terms, leading to more relevant and comprehensive bid discoveries.

## 2. Analysis of the Problem
The current search agent takes user-provided keywords, industry, or region at face value. A user might not be an expert in procurement terminology and could use words that yield poor search results (e.g., "computer work" instead of "IT services"). This limits the effectiveness of the bid discovery process.

## 3. Proposed Solution - Step-by-Step

### Step 1: Modify the Search Agent's Prompt (`SEARCH_RESULT_AGENT_PROMPT`)
**File:** `backend/agents/Bid_Discovery/sub_agents/search_results/prompt.py`

**Action:** I will update the `SEARCH_RESULT_AGENT_PROMPT` to include a new instruction block for "Intelligent Query Refinement." This will guide the agent to think about and improve the user's search terms before executing the search.

**New Prompt Logic to be Added:**
I will insert a new section into the prompt, likely before the `<Navigation & Searching>` step.

```
<Intelligent_Query_Refinement>
- Before searching, take a moment to analyze the user-provided keywords, industry, and region.
- Use your expert knowledge of procurement and various industries to expand these terms. Generate a list of synonyms, related technical terms, and relevant classification codes (like NAICS or UNSPSC) that are likely to produce better search results.
- For example, if a user asks for bids related to "computer work," you should automatically expand your search to include terms like "IT services," "network administration," "cybersecurity," "software development," and "data management."
- You should not ask the user for confirmation. Autonomously use this new, enriched set of keywords to perform a more effective search.
- Your goal is to act as an expert assistant who knows how to find the best opportunities, even if the user doesn't know the exact terms to use.
</Intelligent_Query_Refinement>
```

The existing `<Navigation & Searching>` step will then be updated to use the terms generated from this new step.

### Step 2: Update Change Log
**File:** `backend/agents/Logs/change_logs.md`

**Action:** After successfully implementing the prompt enhancement, I will document the changes in the change log, creating a new entry for this feature.

## 4. Expected Outcome
- The `bid_search_agent` will no longer be limited to the user's exact phrasing.
- The agent will automatically find more relevant bids by searching for a wider, more professional set of terms.
- The user will get better results without needing to be an expert in search-term optimization.
- The overall value of the Bid Discovery feature will be significantly increased. 

# Bid Agent System Refactoring Plan

## 1. Objective
Refactor the agent interaction flow to eliminate redundant information gathering. The "Manager" agent should act as a high-level router, directing users to specialized sub-agents (Search or RAG) without collecting detailed task-specific information itself. The Search agent should be solely responsible for gathering all necessary details for bid discovery and performing the web search.

## 2. Analysis of the Problem
The current implementation has both the main Bid Discovery agent (`backend/agents/Bid_Discovery/agent.py` via `prompt.ROOT_PROMPT`) and the Search agent (`backend/agents/Bid_Discovery/sub_agents/search_results/agent.py` via `prompt.SEARCH_RESULT_AGENT_PROMPT`) asking the user for the same information (procurement portal, keywords, etc.). The main agent also initiates web navigation, which should be the responsibility of the search agent.

This leads to a poor user experience where the user has to provide the same information twice.

## 3. Proposed Solution - Step-by-Step

### Step 1: Modify the Main Agent's Prompt (`ROOT_PROMPT`)
**File:** `backend/agents/Bid_Discovery/prompt.py`

**Action:** Update `ROOT_PROMPT` to remove detailed questions. The agent should only ask the user to choose between "Bid Discovery" and "Document Analysis".

**Current `ROOT_PROMPT`:**
- Asks for keywords, NAICS codes, portal, etc.
- Explicitly calls `bid_search_agent` with parameters.

**New `ROOT_PROMPT`:**
```python
"""
You are a master Bid Strategist agent. Your role is to understand the user's goal and delegate to the appropriate sub-agent.

You have two primary functions available to you:
1.  **Bid Discovery**: Find new bid opportunities on procurement websites.
2.  **Document Analysis**: Analyze an existing bid document to extract key information and answer questions.

Your Steps:
1. Greet the user and ask which of these two functions they would like to perform.
2. If the user chooses "Bid Discovery", delegate the entire task to the `bid_search_agent`.
3. If the user chooses "Document Analysis", delegate the task to the `rag_agent`.
4. Let the selected sub-agent handle all further interaction for their task. Do not ask for any details like keywords or websites yourself.
"""
```

### Step 2: Verify the Search Agent's Prompt (`SEARCH_RESULT_AGENT_PROMPT`)
**File:** `backend/agents/Bid_Discovery/sub_agents/search_results/prompt.py`

**Action:** Ensure the `SEARCH_RESULT_AGENT_PROMPT` is comprehensive and handles the full interaction for bid discovery. This prompt is already well-defined for this purpose and likely needs no major changes. It correctly asks for the portal, keywords, and other details. It also has access to web navigation tools, so it can open the browser tab at the correct time (after gathering information).

### Step 3: Improve Clarity in the Main Agent Definition
**File:** `backend/agents/Bid_Discovery/agent.py`

**Action:** Rename the imported RAG agent to avoid confusion.

**Current Code:**
```python
# ...
from .sub_agents.rag_agent.agent import root_agent

root_agent = Agent(
    # ...
    sub_agents=[
        bid_search_agent,
        root_agent
    ],
)
```

**New Code:**
```python
# ...
from .sub_agents.rag_agent.agent import root_agent as rag_agent

root_agent = Agent(
    # ...
    sub_agents=[
        bid_search_agent,
        rag_agent
    ],
)
```

## 4. Expected Outcome
- The main agent will first ask the user whether they want to "discover bids" or "analyze a document".
- If the user chooses "discover bids", the `bid_search_agent` will be invoked.
- The `bid_search_agent` will then ask for the website, keywords, etc.
- After collecting the information, the `bid_search_agent` will use its tools to open a browser tab and perform the search.
- The user will no longer be asked for the same information multiple times.
- The responsibility of each agent will be clearly separated.


=======
# Master Executable Plan

This document provides a detailed, step-by-step implementation plan for each phase outlined in the project's master plan.

---

## Phase 1: Core Agent Refactoring & Optimization (Executable Plan)

### Objective:
Streamline the agent interaction flow, improve user experience, and optimize resource usage.

#### **Step 1.1: Refactor Main Agent into a High-Level Router**
-   **Action:** Modify the root agent's prompt (`backend/agents/Bid_Discovery/prompt.py`) to remove task-specific questions (e.g., for keywords, portals). The prompt should only ask the user to choose between high-level functions like "Bid Discovery" or "Document Analysis."
-   **Action:** Ensure the agent's logic delegates the entire conversation to the appropriate sub-agent based on the user's choice.

#### **Step 1.2: Implement Lazy Loading for WebDriver**
-   **Action:** In the `search_results` agent (`.../search_results/agent.py`), refactor the Selenium WebDriver initialization.
-   **Action:** Remove the global WebDriver instantiation. Create a `get_driver()` function that initializes the driver as a singleton on its first call.
-   **Action:** Update all browser-related tools (`go_to_url`, `take_screenshot`, etc.) to call `get_driver()` before executing browser commands.

#### **Step 1.3: Enhance Search Agent Intelligence**
-   **Action:** Modify the search agent's prompt (`.../search_results/prompt.py`).
-   **Action:** Add a new instruction step, `<Intelligent_Query_Refinement>`, before the search execution step. This new step commands the agent to use its own knowledge to expand the user's keywords with synonyms and related professional terms.

---

## Phase 2: Hierarchical Agent Architecture (Executable Plan)

### Objective:
Restructure the agent system into a clear hierarchy with a main orchestrator and specialized managers.

#### **Step 2.1: Establish the Top-Level Orchestrator (`root_agent`)**
-   **Action:** Create a main `agent.py` file directly inside `backend/agents/`.
-   **Action:** Define the primary agent in this file and name the variable `root_agent` to comply with `google-adk` framework conventions.
-   **Action:** Create a corresponding `prompt.py` to instruct the `root_agent` to delegate tasks to its specialized manager sub-agents.

#### **Step 2.2: Formalize the `bid_discovery_manager`**
-   **Action:** Convert the existing `Bid_Discovery` agent into a formal manager.
-   **Action:** Rename the agent variable within `backend/agents/Bid_Discovery/agent.py` to `bid_discovery_manager` to reflect its role.

#### **Step 2.3: Centralize Shared Libraries**
-   **Action:** Move the `shared_libraries` directory from its nested location to the top-level `backend/agents/` directory.
-   **Action:** Update all `import` statements in the `root_agent`, `bid_discovery_manager`, and its sub-agents to use the new, corrected relative paths (e.g., `from ..shared_libraries import constants`).

#### **Step 2.4: Ensure Python Packging**
-   **Action:** Create an `__init__.py` file in `backend/agents/` to ensure the directory is treated as a Python package, resolving module loading errors.

---

## Phase 3: PDF Form Filling & Document Automation (Executable Plan)

### Objective:
Introduce document automation capabilities, allowing the system to programmatically create and complete bid forms, even on non-interactive PDFs.

#### **Step 3.1: Add `PyMuPDF` Dependency**
-   **Action:** Add the `PyMuPDF` library to the `backend/requirements.txt` file to enable advanced PDF manipulation.

#### **Step 3.2: Create PDF Manipulation Tools**
-   **Action:** In a new `tools.py` file within `backend/agents/pdf_filler_manager/`, create the necessary functions:
    -   `list_pdf_form_fields(pdf_path)`: To inspect a PDF and find existing form fields.
    -   `find_text_coordinates(pdf_path, text_to_find)`: To find the exact coordinates of a given string on a PDF page.
    -   `create_text_field(pdf_path, ...)`: To programmatically add a new, writable text field to the PDF at specified coordinates.
    -   `fill_pdf_form_field(pdf_path, field_name, value)`: To write data into a field (either existing or newly created).

#### **Step 3.3: Implement the `pdf_filler_manager`**
-   **Action:** Create the `agent.py` and `prompt.py` for the manager inside `backend/agents/pdf_filler_manager/`.
-   **Action:** The prompt must define a branching workflow: If existing fields are found, fill them. If not, use the creation tools to find text labels, create new fields, and then fill them.
-   **Action:** The agent definition must be equipped with all the new PDF tools.

#### **Step 3.4: Integrate the Manager**
-   **Action:** In the main `root_agent` (`backend/agents/agent.py`), import the newly created `pdf_filler_manager` and add it to the `sub_agents` list, making it available for delegation.

---

## Phase 4: UI Integration for Document Automation (Executable Plan)

### Objective:
Provide a seamless frontend user experience for the new PDF filling functionality.

#### **Step 4.1: Create Backend API for File Handling**
-   **Action:** Create a new file, `backend/routes/pdf_routes.py`.
-   **Action:** In this file, define two Flask routes:
    -   **`POST /api/upload-pdf`**: This endpoint will receive a file from the frontend. It will save the file to a secure, temporary directory on the server (e.g., `/tmp/uploads/`) and return the server-side file path as a JSON response (e.g., `{"filePath": "/tmp/uploads/document.pdf"}`).
    -   **`GET /api/download-pdf/<filename>`**: This endpoint will allow the user to download a completed file. It will use Flask's `send_from_directory` to securely serve the file from the temporary directory where filled PDFs are saved.
-   **Action:** Register this new route blueprint in the main Flask `app.py`.

#### **Step 4.2: Develop Frontend UI Components**
-   **Action:** In your frontend application, create a new view or page for "PDF Form Filling."
-   **Action:** Implement a **File Uploader** component. When a user selects a PDF, the component will make a `POST` request to the `/api/upload-pdf` endpoint and store the returned `filePath` in the component's state.
-   **Action:** Implement a **Company Information Form**. This will be a standard web form with input fields for "Company Name," "Address," "EIN," etc.
-   **Action:** Implement a **"Fill Document" Button**. When clicked, this button will trigger the main agent interaction. It will send a message to the `root_agent` that includes:
    -   The user's intent (e.g., "I want to fill a PDF").
    -   The `filePath` obtained from the uploader.
    -   All the data collected from the company information form.
-   **Action:** Implement a **Status and Download** area. After the agent interaction is complete, the final response should contain the path to the new, filled document. The UI will display this and present a "Download Filled PDF" link that points to the `/api/download-pdf/<filename>` endpoint.

# Update 5: PDF Tool Bug Fix

## 1. Objective
Fix the `AttributeError: 'Document' object has no attribute 'save_inplace'` error that occurs when the `pdf_filler_manager` attempts to create a new form field. This will make the PDF creation workflow functional.

## 2. Analysis of the Error
The error is caused by an incorrect method call in the `create_text_field` tool within `backend/agents/pdf_filler_manager/tools.py`. The method `doc.save_inplace()` does not exist in the PyMuPDF library. The correct method to save changes to the same file is `doc.save(pdf_path, incremental=True)`. This allows for a stateful workflow where one tool can create a field and a subsequent tool can fill it within the same PDF file.

## 3. Execution Plan

### **Step 1: Correct the `create_text_field` Tool**
-   **File to Modify:** `backend/agents/pdf_filler_manager/tools.py`
-   **Action:** Locate the `create_text_field` function.
-   **Change:** Replace the line `doc.save_inplace()` with `doc.save(pdf_path, incremental=True)`. This will correctly save the newly created field to the PDF file, allowing the `fill_pdf_form_field` tool to find and populate it in the next step.

# Update 6: Robust PDF Tool Refactoring

## 1. Objective
Fix the workflow-halting error caused by `incremental` saves failing on certain PDFs. This will be achieved by refactoring the PDF tools to be more atomic and robust, ensuring they can handle a wider variety of document types, including those with encryption or non-standard structures.

## 2. Analysis of the Error
The agent's output shows that `doc.save(pdf_path, incremental=True)` is failing. This suggests that appending changes is not a universally reliable method. The current workflow, which relies on one tool creating a field and a second tool filling it, is fragile. A better approach is to combine these actions into a single, atomic tool that always produces a new, clean output file.

## 3. Execution Plan

### **Step 1: Refactor the PDF Tools (`tools.py`)**
-   **File to Modify:** `backend/agents/pdf_filler_manager/tools.py`
-   **Action 1: Remove `create_text_field`**: This tool and its problematic save logic will be removed entirely.
-   **Action 2: Create a New, Atomic Tool**: Introduce a new function: `create_and_fill_field(pdf_path: str, page_number: int, field_name: str, x0: float, y0: float, x1: float, y1: float, value: str) -> str`.
    -   This tool will handle the entire "create and fill" process in one step.
    -   It will open the PDF, create the widget, set its value, add it to the page, and crucially, **save the output to a new file** (e.g., `original_name_filled.pdf`).
    -   It will return a confirmation message with the path to this new file.
-   **Action 3: Standardize `fill_pdf_form_field`**: Ensure the existing `fill_pdf_form_field` tool also follows the same "save to new file" pattern to maintain consistent behavior. (It already does this, so a review is sufficient).

### **Step 2: Simplify the Agent's Prompt (`prompt.py`)**
-   **File to Modify:** `backend/agents/pdf_filler_manager/prompt.py`
-   **Action:** Rewrite "Workflow B: Create and Fill New Fields".
-   **Change:** Instead of the complex, multi-step process of finding coordinates, creating a field, and then filling it, the agent will now be instructed to do the following for each piece of data:
    1.  Use `find_text_coordinates` to get the location.
    2.  Use the new, single `create_and_fill_field` tool to perform the modification.
-   This makes the agent's logic simpler and less prone to state-related errors.

### **Step 3: Update the Agent's Toolset (`agent.py`)**
-   **File to Modify:** `backend/agents/pdf_filler_manager/agent.py`
-   **Action:** Update the list of tools assigned to the `pdf_filler_manager`.
-   **Change:** Remove `create_text_field` and add the new `create_and_fill_field` tool.

# Bid Agent Update Log - 2024-07-22

## Issue: Agent fails to interact with search filters on SAM.gov

The Bid Discovery agent is unable to interact with input fields on SAM.gov, preventing it from performing searches. The root cause is the brittleness of the element selectors used by the Selenium-based web browsing tools in `backend/agents/Bid_Discovery/sub_agents/search_results/agent.py`. The current implementation relies on finding elements by their `ID` or by exact text match, which is unreliable on modern web applications like SAM.gov.

## Plan for Resolution

To address this issue, I will enhance the web browsing tools to use more robust methods for locating and interacting with web elements.

### 1. Improve Element Identification Strategy

I will modify the core element finding logic to use a chain of increasingly flexible selectors. Instead of relying on a single method, the agent will try multiple strategies to find an element. The order of strategies will be:

1.  Find by `ID`
2.  Find by `name` attribute
3.  Find by CSS Selector
4.  Find by XPath (using more flexible queries)

This will make the agent more resilient to changes in the website's structure.

### 2. Enhance Existing Web Browsing Tools

I will refactor the existing `enter_text_into_element` and `click_element_with_text` functions to incorporate the new element identification strategy.

-   **`enter_text_into_element(selector: dict, text_to_enter: str)`**: This function will be updated to accept a dictionary specifying the selector strategy and value (e.g., `{'css': '.search-input'}`).

-   **`click_element_with_text(text: str)`**: This function will be updated to use XPath's `contains()` function for partial text matches, making it less brittle.

### 3. Add a New Tool for Form Interaction

I will create a new tool, `enter_text_into_element_by_label(label_text: str, text_to_enter: str)`. This tool will first locate a `<label>` element containing the given `label_text` and then find the associated `input` field to enter the text into. This is a highly robust method for interacting with web forms.

### 4. Improve Logging and Debugging

To facilitate future debugging, I will add more detailed logging to the web browsing tools. When an element cannot be found, the agent will automatically save the current page source and a screenshot. This will provide valuable context for diagnosing issues.

By implementing these changes, the Bid Discovery agent will be more capable of navigating and interacting with complex web pages, leading to a more reliable bid discovery process.


# Update 7: Unified PDF Document Automation & Form Field Workflow

## 1. Objective
Establish a seamless, extensible workflow for PDF document automation, enabling the orchestrator agent to route PDF-related tasks to a manager agent, which then delegates to specialized sub-agents for form field detection, creation, and filling. The workflow supports both interactive (with form fields) and non-interactive (scanned or flat) PDFs, using Document AI and OCR tools as appropriate.

## 2. Analysis of the Problem
Previous implementations separated PDF form filling and form field detection, lacking a unified, user-friendly workflow. There was no clear, extensible agent hierarchy for handling the decision logic between digital and scanned PDFs, nor a standardized way to store and pass form field information for downstream filling.

## 3. Executable Plan - Step-by-Step

### Step 1: Orchestrator Agent Enhancement
- **File:** `backend/agents/agent.py`, `backend/agents/prompt.py`
- **Action:** Update the root orchestrator agent to recognize when the user wants to perform PDF automation. Add logic to transfer the user to the `document_automation_manager` when such a request is detected.

### Step 2: Document Automation Manager Workflow
- **File:** `backend/agents/document_automation_manager/agent.py`, `prompt.py`
- **Action:** The manager agent should:
    1. Prompt the user for the PDF file, its MIME type, and whether it contains form fields.
    2. Based on the user's response:
        - If the PDF has form fields, delegate to the digital form field tools (Document AI sub-agent).
        - If the PDF does not have form fields, delegate to the OCR sub-agent to detect potential form field locations.
    3. Store the detected or extracted form field information in a standardized JSON format for downstream use.

### Step 3: Specialized Sub-Agent Delegation
- **File:** `backend/agents/document_automation_manager/sub_agents/`
- **Action:**
    - Use the `docai_tool_agent` for digital PDFs with form fields (Document AI extraction).
    - Use the `ocr_tool_agent` for scanned/flat PDFs (OCR-based field detection).
    - Use the `json_formatter_agent` to standardize the output as a JSON array of form fields (excluding signature fields).
    - Use the `pdf_filler_agent` to fill out the PDF using the JSON field data, if/when the user provides values.

### Step 4: JSON Field Storage and Handoff
- **File:** (as needed, e.g., in manager or shared libraries)
- **Action:** Ensure the output from field detection (digital or OCR) is stored in a JSON structure, ready for the PDF filler agent to consume. This enables a clean separation between field detection/creation and field filling.

### Step 5: Maintain Cohesive Agent Structure
- **Action:**
    - The orchestrator only routes to the document automation manager.
    - The manager handles user interaction and delegates to sub-agents based on document type.
    - Sub-agents handle specialized tasks (field detection, JSON formatting, filling).
    - All agents and tools should be modular and extensible for future enhancements (e.g., new field types, improved OCR, etc.).

## 4. Summary of Previous Phases (for context)

- **Phase 1:** Core agent refactoring and optimization (high-level router, lazy WebDriver, intelligent query refinement).
- **Phase 2:** Hierarchical agent architecture (root orchestrator, manager agents, centralized shared libraries, Python packaging).
- **Phase 3:** PDF form filling and document automation (PyMuPDF tools, PDF filler manager, branching workflow for field creation/filling).
- **Phase 4:** UI integration for document automation (backend API for file handling, frontend components for upload/fill/download).
- **Update 5 & 6:** Robust PDF tool bug fixes and refactoring (atomic field creation/filling, improved error handling).

## 5. Expected Outcome
- Users interact with the orchestrator as usual and can request PDF automation.
- The orchestrator transfers control to the document automation manager, which collects the PDF, MIME type, and field presence info.
- The manager delegates to the appropriate sub-agent (Document AI or OCR) for field detection/creation.
- Form field data is stored in a standardized JSON format, ready for the PDF filler agent to complete the document.
- The agent structure is modular, extensible, and future-proofed for additional document automation features.

# Bid Agent Update & Strategy Log

## Phase 5: A New Strategy for High-Performance Field Detection

### The Problem
Despite multiple iterations, the agent is unable to reliably and quickly identify all fillable fields from visual cues (i.e., underscore lines `_________`). The agent's dialogue shows a total failure across all three tiers of its strategy, resulting in no fields being found. This indicates our previous approaches have been fundamentally flawed.

### 1. Root Cause Analysis & Lessons Learned

Our journey has been a series of trials that have revealed critical truths:

*   **Google Cloud Tools are Unsuitable for this Task:**
    *   **`analyze_document_with_docai` (Form Parser):** This tool is designed for structured PDF forms (AcroForms) and is blind to visual cues like underscore lines. It consistently and correctly finds nothing in our target document.
        *   **Conclusion:** This tool is not fit for this purpose and should be deprecated from this workflow.
    *   **`run_ocr_and_extract_fields` (Cloud OCR):** This tool is *too* intelligent. It correctly identifies `_________` as a graphical line, not a string of text characters. As a result, it reports "no underscore characters found."
        *   **Conclusion:** This tool, while powerful, is the wrong tool for finding underscore-based fields.

*   **The Local Heuristic (`extract_fields_with_local_heuristics`) is Our Only Viable Path:**
    *   The `PyMuPDF` library is the **only** tool that has shown any success in identifying both text-based underscores and vector graphics. Every small victory has come from this tool. Our failures have stemmed from how we used it.

*   **Performance is the True Enemy:**
    *   The most capable version of our local tool, which searched for text and vector drawings (`page.get_drawings()`), was unacceptably slow because it had to inspect every single graphical object on the page.
    *   My subsequent attempt to "optimize" this by searching only in "empty zones" was a catastrophic logical error. It made the agent blind to the vast majority of the page, causing the current total failure.

### 2. The New, Definitive Plan: High-Speed Vector Analysis

The slow performance of a full-page drawing analysis is the final obstacle. We will defeat it not by avoiding it, but by replacing it with a far superior weapon from the `PyMuPDF` arsenal, combined with a new technique. This mirrors the likely approach of professional, high-speed tools like Apple's.

*   **Step 1: Abandon Generic `get_drawings()` for a Specialized Approach.** We will stop using the slow, generic `page.get_drawings()` method.

*   **Step 2: Isolate All Vector Graphics Instantly.** We will use `page.get_image_info(vectors=True)` to generate a clean, high-resolution image containing *only* the vector graphics (lines, rectangles, etc.), with all text removed. This is an incredibly fast and efficient way to get a "tracing" of the page's structure.

*   **Step 3: Use Computer Vision to Find Lines.** On this clean "vector image," we will use a lightweight, fast computer vision library (`opencv-python-headless`) to instantly find all horizontal lines using a Hough Line Transform. This is what computer vision is built for and is orders of magnitude faster than iterating through PDF objects.

*   **Step 4: Correlate Lines with Text.** Once we have the precise coordinates of all lines from the computer vision analysis, we will correlate them with the page's text (obtained via the fast `page.get_text("words")` method) to find their labels.

*   **Step 5: Merge with Text-Based Underscores.** We will still run our fast, text-only search for `_` characters as a parallel strategy. The results from both the computer vision analysis and the text search will be merged to create one complete, final list of fields.

### 3. Execution Path

1.  **Update Dependencies:** Add `opencv-python-headless` and `numpy` to `backend/requirements.txt` to enable high-speed computer vision analysis.
2.  **Overhaul `extract_fields_with_local_heuristics`:** Completely rewrite the function to implement the new High-Speed Vector Analysis plan.
3.  **Simplify Agent Prompt:** The agent's tiered strategy is overly complex and has failed. We will simplify the prompt to **only** use the new, powerful local heuristic tool. The other cloud tools will be removed from the primary workflow to prevent the agent from making incorrect choices on this type of document.

This plan is robust, addresses the root cause (performance), and is based on a sound technical approach that will deliver the speed and accuracy we require.

# Update 7: Explicit Underscore Blueprint

## 1. Objective
To significantly improve the clarity and accuracy of the form field identification process. The agent will be updated to explicitly capture the raw underscore text (`"_______"`) from the document, include it in the generated JSON blueprint, and present it to the user in its summary.

## 2. Analysis of the Problem
The current heuristic-based field identification is struggling. It often misidentifies the text label associated with an underscore line, leading to confusing and inaccurate field names. The user has no way to verify which visual field on the PDF corresponds to the name the agent has generated. By capturing the underscore text itself, we create a direct visual anchor between the blueprint and the original document.

## 3. Execution Plan

### Step 1: Enhance the Field Extraction Logic (`tools.py`)
-   **File to Modify:** `backend/agents/document_automation_manager/tools.py`
-   **Function to Modify:** `run_ocr_and_extract_fields`
-   **Action 1: Capture Raw Underscore Text:** During the "Merge adjacent underscore tokens" step, in addition to merging the bounding boxes, I will concatenate the `text` of each token. This will create a string like `"_____________"`.
-   **Action 2: Update the JSON Blueprint Structure:** I will add a new key, `placeholder_text`, to the JSON object created for each form field. This key will hold the concatenated underscore string. The final field object will look like this:
    ```json
    {
      "field_name": "Name",
      "placeholder_text": "____________________",
      "field_type": "text",
      "page_number": 1,
      "coordinates": [...]
    }
    ```

### Step 2: Update the Agent's Prompt (`prompt.py`)
-   **File to Modify:** `backend/agents/document_automation_manager/prompt.py`
-   **Section to Modify:** `Part 2: Confirm & Request Data`
-   **Action:** I will modify the prompt to instruct the agent to use this new `placeholder_text`. The agent's summary to the user should now include both the field name and the placeholder.
-   **New Prompt Instruction:**
    > "Announce that the blueprint was created, provide the captured path, and list the fields found. For each field, display both the `field_name` and its corresponding `placeholder_text` to give the user clear visual context (e.g., `Field 'BID OF': _________________`). Then, ask the user for the data to fill them."

## 4. Expected Outcome
-   The JSON blueprint will be more robust and contain the exact underscore text for each field.
-   The agent's summary will be far more intuitive. The user will be able to look at the agent's output and immediately see which line on the PDF it corresponds to.
-   This will dramatically improve the user experience and the overall accuracy of the form-filling process.

# Update Logs

## 2024-07-16: Plan for Intelligent Form Field Extraction

The OCR output using native PDF parsing is now highly accurate and reliably includes underscore characters. The next step is to implement a robust strategy to convert this raw text into a structured JSON blueprint for form field creation.

### The Plan

The core challenge is to translate the raw text, which contains lines of underscores, into a structured JSON "blueprint" that defines the name, location, and page number for each form field. Since we have the full Document AI `document` object available (which contains text, tokens, and their coordinates), we can implement a robust, token-based strategy.

1.  **Restore and Refine the `run_ocr_and_extract_fields` Function:**
    *   The function in `backend/agents/document_automation_manager/tools.py` will be restored to its purpose of *extracting fields*, not just dumping debug info.
    *   It will continue to use the `enable_native_pdf_parsing` option, as this provides the high-quality text we're now seeing.

2.  **Implement Token-Based Field Detection Logic:**
    The previous implementation was on the right track but had flaws in associating labels with fields. A new, more resilient version will be written with the following logic for each page in the document:
    *   **Partition Tokens:** Iterate through every token on the page. A token is the smallest unit of text with coordinate data (e.g., a single word or a group of underscores).
        *   If a token consists primarily of underscores (e.g., `_`, `___`, `_______`), classify it as a `field_token`.
        *   All other tokens are classified as `label_tokens`.
    *   **Merge Field Tokens:** A single fillable line might be recognized as multiple, adjacent `field_tokens`. These will be merged into a single logical field area by combining their bounding boxes. This correctly handles long lines of `_________`.
    *   **Associate Labels with Fields:** For each merged field area, find the most plausible text label. The logic will search for `label_tokens` that are:
        *   **To the Left:** Immediately preceding the field on the same horizontal line.
        *   **Directly Above:** On the line immediately above the field, in vertical alignment.
        This dual-check approach correctly handles common form layouts.
    *   **Filter Out Signatures:** Any identified field whose label contains "signature", "signatory", or similar terms will be ignored to prevent creating fields in signature blocks.

3.  **Construct the JSON Blueprint:**
    *   For each valid field found, a JSON object will be created containing:
        *   `field_name`: The cleaned text label (e.g., "BID OF").
        *   `page_number`: The page the field was found on.
        *   `coordinates`: The bounding box of the merged underscore area.
        *   `placeholder_text`: The raw underscore text (e.g., "_________________"), which is useful for user verification.
    *   The function will return a final JSON array of these objects, which the agent can then use to create the PDF form.

This plan is robust because it doesn't rely on fragile line-by-line parsing. By operating on tokens and their coordinates, it can handle complex layouts where labels and fields are not perfectly aligned.

## Update 12: The Loop Break and Restoration of Field Checking

1.  **Stabilize the Azure Tool:** The infinite loop originates from the `azure_tool_agent`. The tool that calls Azure's analysis service appears to be returning a "processing" status instead of waiting for the final result. I will modify the `analyze_document_layout` tool to ensure it's a synchronous, blocking operation from the agent's perspective. It will only return the complete and final JSON from Azure, or an error, never an intermediate status. This will prevent the `document_automation_manager` from re-triggering it.

2.  **Fortify the Manager's Logic:** The `document_automation_manager`'s prompt will be further refined. I will make its workflow even more rigid and explicit to prevent any ambiguity. The new logic will be:
    *   **State 1 (Check Fields):** Use the `list_existing_pdf_fields` tool.
    *   **State 2 (Analyze Layout):** If and only if State 1 returns no fields or fails, delegate **once** to `azure_tool_agent`.
    *   **State 3 (Create Blueprint):** If and only if State 2 succeeds, delegate **once** to `json_formatter_agent` with the result.
    *   **State 4 (End):** Report the final output and terminate.

3.  **Address Field Checking Degradation:** The field-checking is "not the same as before." The current tool returns a natural language string (`"Found existing form fields: ..."`, `"No existing...found"`, or an error message). This is likely too ambiguous for the LLM to handle reliably. I will modify the `list_existing_pdf_fields` tool to return a structured JSON string instead (e.g., `{"status": "success", "fields": ["field1", "field2"]}` or `{"status": "no_fields_found"}` or `{"status": "error", "message": "..."}`). This will make the output machine-readable and allow the manager agent to make a more deterministic decision.
