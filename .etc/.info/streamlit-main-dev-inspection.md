# Project Inspection Report: RB Loan Deferment IDP (`main-dev`)

## 1. Overview
**Project Name**: RB Loan Deferment IDP (Intelligent Document Processing)
**Location**: `apps/main-dev`
**Purpose**: To automate the validation of loan deferment applications by analyzing uploaded supporting documents (PDFs/Images). It verifies that the document matches the applicant (FIO), is of a valid type, is current (date validity), and optionally contains a stamp.

## 2. Architecture & Flow
The application follows a linear pipeline architecture orchestrated by a central controller, triggered by a Streamlit UI.

### High-Level Data Flow
1.  **User Input**: User uploads a file and enters their FIO via the Streamlit UI.
2.  **Acquisition**: File is saved, and basic checks (page count) are performed.
3.  **OCR**: Text is extracted from the document using an asynchronous Tesseract service.
4.  **Analysis (Parallel/Sequential)**:
    *   **Doc Type Check**: LLM analyzes text to classify the document type.
    *   **Extraction**: LLM extracts structured data (FIO, Document Date).
    *   **Stamp Detection**: (Optional) Computer Vision model detects stamps.
5.  **Merge**: Results from all analysis stages are combined.
6.  **Validation**: Extracted data is compared against user input and business rules (validity periods).
7.  **Output**: A final verdict (True/False), error codes, and detailed diagnostics are returned to the UI.

## 3. Directory Structure
```
apps/main-dev/rb-ocr/
├── app.py                      # Entry point: Streamlit UI
├── main.py                     # Dev/Test script (bypasses UI)
├── pipeline/
│   ├── orchestrator.py         # Core logic: Defines pipeline stages and flow
│   ├── clients/                # External service wrappers
│   │   ├── llm_client.py           # Internal LLM endpoint wrapper
│   │   ├── tesseract_async_client.py # Async OCR service wrapper
│   │   └── textract_client.py      # (Legacy/Unused) AWS Textract client
│   ├── core/                   # Configuration and domain logic
│   │   ├── config.py               # Global constants (paths, limits)
│   │   ├── errors.py               # Centralized error codes & messages (RU)
│   │   ├── validity.py             # Document validity logic (expiration rules)
│   │   ├── dates.py                # Date parsing helpers
│   │   └── settings.py             # Environment settings
│   ├── models/                 # Data structures
│   │   └── dto.py                  # Pydantic models for typed data exchange
│   ├── processors/             # Business logic units
│   │   ├── validator.py            # Final decision logic (Verdict calculation)
│   │   ├── fio_matching.py         # Advanced FIO comparison (Fuzzy + Deterministic)
│   │   ├── stamp_check.py          # Wrapper for external stamp detection script
│   │   ├── agent_doc_type_checker.py # LLM Agent for classification
│   │   ├── agent_extractor.py      # LLM Agent for data extraction
│   │   ├── merge_outputs.py        # Combines LLM & OCR results
│   │   ├── filter_ocr_response.py  # Normalizes OCR output
│   │   ├── filter_llm_generic_response.py # Normalizes LLM JSON output
│   │   └── image_to_pdf_converter.py # Helper for image uploads
│   ├── prompts/                # LLM Instructions
│   │   ├── dtc/v1.prompt.txt       # Prompt for Document Type Classification
│   │   └── extractor/v1.prompt.txt # Prompt for FIO/Date Extraction
│   └── utils/                  # Shared utilities
│       ├── artifacts.py            # Generates JSON outputs (manifest, results)
│       ├── io_utils.py             # File I/O helpers
│       └── timing.py               # Performance profiling helpers
└── runs/                       # Runtime artifacts (created during execution)
```

## 4. Component Deep Dive

### 4.1. User Interface (`app.py`)
*   **Framework**: Streamlit.
*   **Function**:
    *   Accepts `FIO` (text input) and `File` (uploader).
    *   Invokes `pipeline.orchestrator.run_pipeline`.
    *   Displays results: Success/Error banner, list of specific errors (mapped from codes), and expandable JSON diagnostics (`final_result.json`, `side_by_side.json`).
    *   **Recent Change**: `reason` and `doc_type` inputs were removed to simplify the flow.

### 4.2. Orchestrator (`pipeline/orchestrator.py`)
*   **Role**: The "brain" of the system. It initializes a `PipelineContext` and executes stages in order.
*   **Stages**:
    1.  `stage_acquire`: Saves file, checks PDF page limit (`MAX_PDF_PAGES`).
    2.  `stage_ocr`: Calls `ask_tesseract`, filters response to `ocr_pages.json`.
    3.  `stage_doc_type_check`: Calls `check_single_doc_type` (LLM), saves `llm_doc_type.json`.
    4.  `stage_extract_and_stamp`: Calls `extract_doc_data` (LLM) and `stamp_present_for_source`.
    5.  `stage_merge`: Combines all intermediate JSONs into `merged.json`.
    6.  `stage_validate_and_finalize`: Runs `validate_run` to produce `final_result.json`.
*   **Error Handling**: Catches exceptions at each stage, logs them, and calls `fail_and_finalize` to ensure a structured error response is always returned.

### 4.3. Processors (The "How")
*   **OCR (`tesseract_async_client.py`)**:
    *   Uses an internal ForteBank OCR service (`ocr.fortebank.com`).
    *   Asynchronous polling mechanism.
    *   Handles image-to-PDF conversion if needed.
*   **LLM Agents (`agent_*.py`)**:
    *   Construct prompts by injecting OCR text into templates from `pipeline/prompts/`.
    *   Call `llm_client.py` (internal OpenAI-compatible endpoint).
    *   **Doc Type Checker**: Classifies document against a known list (e.g., "Больничный лист").
    *   **Extractor**: Extracts `fio` and `doc_date`.
*   **FIO Matching (`fio_matching.py`)**:
    *   **Sophisticated Logic**: Handles Cyrillic/Latin lookalikes, KZ specific characters, and name variants (Full, Initials, etc.).
    *   **Methods**: Uses both deterministic normalization (canonical forms) and fuzzy matching (`rapidfuzz`/`difflib`).
*   **Validation (`validator.py`)**:
    *   **Core Rules**:
        *   `fio_match`: Extracted FIO must match User FIO.
        *   `doc_type_known`: Document type must be recognized.
        *   `doc_date_valid`: Document must not be expired (logic in `validity.py`).
        *   `single_doc_type_valid`: Only one document type detected.
        *   `stamp_present`: (If enabled) Stamp must be detected.
    *   **Verdict**: All checks must be `True` for a positive verdict.

### 4.4. Data & Configuration
*   **Config (`config.py`)**:
    *   `MAX_PDF_PAGES`: 3 (Performance guardrail).
    *   `STAMP_ENABLED`: Toggle via env var `STAMP_ENABLED`.
*   **Validity (`validity.py`)**:
    *   Defines expiration rules for specific document types (e.g., "Справка" valid for 10-30 days).
*   **Errors (`errors.py`)**:
    *   Maps internal error codes (e.g., `DOC_DATE_TOO_OLD`) to user-friendly Russian messages.

## 5. Artifacts (Outputs)
For every run, a directory is created in `runs/YYYY-MM-DD/<run_id>/`. Key files:
*   `metadata.json`: User inputs (FIO).
*   `ocr/ocr_pages.json`: Raw text from OCR.
*   `llm/merged.json`: Combined extracted data.
*   `validation/validation.json`: Detailed check results.
*   `meta/final_result.json`: Public output (Verdict + Error Codes).
*   `meta/side_by_side.json`: Debug view comparing User Input vs. Extracted Data.
*   `meta/manifest.json`: Operational summary (timings, paths).

## 6. Key Observations
*   **Robustness**: The pipeline is defensive. It handles missing dependencies (e.g., `pydantic` fallback in `dto.py`), wraps external calls in try/except blocks, and ensures artifacts are written even on failure.
*   **Modularity**: Components are well-separated. Replacing the OCR provider or LLM model would only require changing the respective client/agent files.
*   **Traceability**: The `runs/` directory structure provides a complete audit trail for every request, which is crucial for debugging IDP systems.
