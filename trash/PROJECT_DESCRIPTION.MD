# RB Loan Deferment IDP (apps/) – Project Description

## What this project is
- **Purpose**: Verify supporting documents for a borrower’s loan deferment request via OCR + LLM and business validation.
- **Users**: Back-office or operational staff uploading a single file (PDF/JPG/PNG/JPEG) for automated checks.
- **Output**: A verdict, human-readable errors, and diagnostic artifacts per run.

## High-level architecture
- **Streamlit UI** (apps/main/rbocr/app.py, apps/main-dev/rb-ocr/app.py)
  - Inputs: `fio` (ФИО), `reason` (Причина), `doc_type` (Тип документа), and a single file upload.
  - Displays: Verdict, error messages, side-by-side comparison, SLA metrics, and optional stamp visualization.
- **Orchestrator** (rbidp/orchestrator.py)
  - Manages a full run: storage, OCR, LLM calls, merging, stamp detection, validation, and manifesting.
- **Clients** (rbidp/clients)
  - `tesseract_async_client.py`: Async HTTP client for Dev OCR service (Tesseract) with auto image→PDF conversion.
  - `gpt_client.py`: Internal DMZ GPT completions API client.
  - `textract_client.py`: Legacy OCR client kept for reference.
- **Processors** (rbidp/processors)
  - OCR page filtering, LLM prompts (doc-type checker and extractor), generic GPT response filter, merge, validation, stamp detection.
- **Core** (rbidp/core)
  - `config.py`: File names and constants (e.g., MAX_PDF_PAGES=3, UTC_OFFSET_HOURS=5).
  - `errors.py`: Stable error codes/messages.
  - `dates.py`, `validity.py`: Date parsing and policy-driven validity windows.

## Repository layout (apps/)
- `main/`
  - `rbocr/app.py`: Production-facing Streamlit app.
  - `rbocr/main.py`: Ad-hoc/test entry (not used by UI).
  - `rbocr/rbidp/`: Shared pipeline library.
- `main-dev/`
  - `rb-ocr/app.py`: Dev Streamlit app (title includes [DEV]).
  - `rb-ocr/rbidp/`: Same library (dev paths for stamp detector).
- This description: `PROJECT_DESCRIPTION.MD` (you are here).

## End-to-end processing flow
1. **Run directory setup**
   - A run ID like `YYYYMMDD_HHMMSS_<id>` is created under `runs/<date>/<run_id>/` with subfolders: `input/original`, `ocr`, `gpt`, `meta`.
   - Input file is copied to `input/original`.
2. **Pre-checks**
   - If PDF pages > `MAX_PDF_PAGES` (3), early error `PDF_TOO_MANY_PAGES`.
3. **OCR** (Tesseract async over Dev OCR)
   - `ask_tesseract(...)` uploads file; optionally converts images to PDF first.
   - Raw OCR JSON is saved as `ocr/ocr_response_raw.json`.
   - `filter_ocr_response(...)` produces `ocr/ocr_response_filtered.json` with simplified page texts: `{ "pages": [{"page_number", "text"}, ...] }`.
4. **Doc-type single check** (LLM)
   - Prompted via `agent_doc_type_checker.check_single_doc_type(pages_obj)`.
   - Raw LLM output string is saved then normalized by `processors/filter_gpt_generic_response.py` to `gpt/gpt_doc_type_check_filtered.json`.
   - Expects: `{ "single_doc_type": boolean, "detected_doc_types": [str], "reasoning": str }`.
   - If not parseable → `DTC_PARSE_ERROR`. If multiple → `MULTIPLE_DOCUMENTS` (early stop).
5. **Extraction** (LLM)
   - `agent_extractor.extract_doc_data(pages_obj)` extracts:
     - `fio`, `doc_type`, `doc_date`, `valid_until` (only for decree order; else null).
   - Filtered output saved as `gpt/gpt_extractor_response_filtered.json`.
   - Schema validated with informative `EXTRACT_SCHEMA_INVALID` on mismatch; generic `EXTRACT_FAILED` on exceptions.
6. **Stamp detection** (optional, non-fatal)
   - External `stamp-processing` script is executed with absolute paths (differs in main vs main-dev).
   - For PDF, renders pages into one tall JPG using PyMuPDF, runs detector, copies `*_with_boxes.jpg` into `input/original/` for UI preview.
   - Persists `{ "stamp_present": bool }` to `meta/stamp_check_response.json` if available.
7. **Merge**
   - `processors/merge_outputs.py` merges extractor + doc-type checker (+ optional stamp result) into `gpt/merged.json`.
   - Additionally writes `meta/side_by_side.json` to compare user input vs extracted values and include policy-based `valid_until`.
8. **Validation**
   - `processors/validator.py` computes checks and verdict:
     - `fio_match`: RapidFuzz token_sort_ratio≥90 after KZ→RU transliteration and Latin→Cyrillic normalization.
     - `doc_type_match`: exact match to selected type.
     - `doc_date_valid`: computed by policy (see below).
     - `single_doc_type_valid`: must be true.
     - `stamp_present`: must be true (tri-state; required for final verdict).
   - All five must be True for final `verdict=True`.
9. **Final artifacts**
   - `meta/final_result.json`: Minimal public result with `run_id`, `verdict`, `errors` (only codes), and optional `stamp_present`.
   - `meta/manifest.json`: Timing (`duration_seconds`, `stamp_seconds`, `ocr_seconds`, `gpt_seconds`), pointers to artifacts, user input & file info, status.
   - UI reads `final_result.json`, `side_by_side.json`, and `manifest.json` for presentation.

## Document types and policies
- Canonical doc types (used in prompts and matching), e.g.:
  - Лист временной нетрудоспособности (больничный лист)
  - Приказ о выходе в декретный отпуск по уходу за ребенком
  - Справка о выходе в декретный отпуск по уходу за ребенком
  - Выписка из стационара (выписной эпикриз)
  - Больничный лист на сопровождающего (если предусмотрено)
  - Заключение врачебно-консультативной комиссии (ВКК)
  - Справка об инвалидности
  - Справка о степени утраты общей трудоспособности
  - Приказ/Справка о расторжении трудового договора
  - Справка о регистрации в качестве безработного
  - Приказ работодателя о предоставлении отпуска без сохранения заработной платы
  - Справка о неполучении доходов
  - Уведомление о регистрации в качестве лица, ищущего работу
  - Лица, зарегистрированные в качестве безработных
- Validity policy (`rbidp/core/validity.py`):
  - Default: 30 days from `doc_date`.
  - ВКК: 180 days; Инвалидность: 360 days; Утрата трудоспособности: 360 days.
  - Декретный приказ: uses explicit `valid_until` from text if present.

## Error codes (examples)
- Acquisition/UI: `PDF_TOO_MANY_PAGES`, `FILE_SAVE_FAILED`.
- OCR: `OCR_FAILED`, `OCR_FILTER_FAILED`, `OCR_EMPTY_PAGES`.
- Doc-type check: `DTC_FAILED`, `DTC_PARSE_ERROR`, `MULTIPLE_DOCUMENTS`.
- Extraction: `EXTRACT_FAILED`, `EXTRACT_SCHEMA_INVALID`, `GPT_FILTER_PARSE_ERROR`.
- Merge/Validation: `MERGE_FAILED`, `VALIDATION_FAILED`.
- Derived checks: `FIO_MISMATCH`, `FIO_MISSING`, `DOC_TYPE_MISMATCH`, `DOC_TYPE_MISSING`, `DOC_DATE_TOO_OLD`, `DOC_DATE_MISSING`, `SINGLE_DOC_TYPE_INVALID`, `STAMP_NOT_PRESENT`, `STAMP_CHECK_MISSING`.

## External services and paths
- **Dev OCR (Tesseract)**: `https://dev-ocr.fortebank.com/v2`
  - Used via `rbidp/clients/tesseract_async_client.py` with async polling.
- **DMZ GPT Completions**: `https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2`
  - Called by `rbidp/clients/gpt_client.py`. SSL verification is disabled via `_create_unverified_context()` to tolerate self-signed certs.
- **Stamp detector** (external Python app + weights):
  - main:     `/home/rb_admin2/apps/main/stamp-processing/{.venv/bin/python, main.py, weights/stamp_detector.pt}`
  - main-dev: `/home/rb_admin2/apps/main-dev/stamp-processing/{.venv/bin/python, main.py, weights/stamp_detector.pt}`
  - The detector returns `result.json` with `{"stamp_present": bool}` and a visualization image `*_with_boxes.jpg`.

## Outputs per run (example)
- runs/YYYY-MM-DD/<run_id>/
  - input/original/
    - <uploaded_file>
    - <uploaded_file>_with_boxes.jpg (if stamp vis available)
  - ocr/
    - ocr_response_raw.json
    - ocr_response_filtered.json
  - gpt/
    - gpt_doc_type_check_filtered.json
    - gpt_extractor_response_filtered.json
    - merged.json
  - meta/
    - metadata.json (fio, reason, doc_type from UI)
    - stamp_check_response.json (optional)
    - side_by_side.json (compact comparison for UI)
    - final_result.json (verdict + error codes)
    - manifest.json (timings, artifacts, status)

## How to run
- Install Python packages (indicative):
  ```bash
  pip install streamlit httpx rapidfuzz pypdf PyPDF2 pillow pymupdf
  ```
  - For stamp detection: external app + weights must exist at the configured absolute paths, or stamp check will return `None`.
- Start the UI:
  - Dev:
    ```bash
    streamlit run apps/main-dev/rb-ocr/app.py
    ```
  - Main:
    ```bash
    streamlit run apps/main/rbocr/app.py
    ```
- Notes:
  - The app creates `runs/` inside the app folder automatically.
  - Network access to Dev OCR and DMZ GPT endpoints is required.

## Configuration points
- `rbidp/core/config.py`
  - Filenames, `MAX_PDF_PAGES=3`, `UTC_OFFSET_HOURS=5` (used for timestamps and validity localization).
- `rbidp/clients/gpt_client.py`
  - DMZ endpoint URL, model (`gpt-4o-mini`), temperature, max_tokens. SSL verification disabled intentionally for self-signed certs.
- `rbidp/clients/tesseract_async_client.py`
  - Dev OCR base URL, verify flag, poll interval, and timeouts. Auto conversion of images to PDF via Pillow.
- `rbidp/processors/stamp_check.py`
  - Absolute paths to detector python, entry script, and weights differ between main and main-dev.

## main vs main-dev
- **UI**: Dev’s title is prefixed with `[DEV]`.
- **Stamp detector paths**: point to different directories: `apps/main/...` vs `apps/main-dev/...`.
- **Orchestrator/Config**: Logic and constants are otherwise in sync across folders.

## Limitations and notes
- PDF page limit is strict (3 pages).
- Extraction relies on LLM prompt adherence; generic filter normalizes OpenAI-like responses into pure JSON dicts.
- Stamp detection is optional; if unavailable, the corresponding check becomes `None` and may affect the final verdict (requires True for success).
- Name matching uses transliteration and fuzzy matching; threshold 90.

## Files of interest
- UI: `app.py`
- Pipeline: `rbidp/orchestrator.py`
- Clients: `rbidp/clients/{tesseract_async_client.py,gpt_client.py,textract_client.py}`
- Processors: `rbidp/processors/*` (filters, prompts, merge, validator, stamp_check, image_to_pdf)
- Core: `rbidp/core/{config.py,errors.py,dates.py,validity.py}`

## Security/Compliance considerations
- GPT client ignores SSL verification for internal DMZ endpoint (self-signed certs). Review before production hardening.
- External stamp detector uses subprocess execution of a Python script with a local venv and absolute paths; ensure controlled environment.
- Uploaded files are copied into `runs/` for diagnostics; plan retention/cleanup according to policy.
