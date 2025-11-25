# RB Loan Deferment IDP (main-dev) — Architecture and Operations Report

This document explains how the project works end-to-end for technical leads and reviewers. It covers the runtime architecture, pipeline stages, data/artifact layout, external integrations, configuration, validation logic, error handling, and next steps for bank integration.

## 1) Overview

- **Purpose**: Automate document intake for loan deferment by combining OCR and LLM-based extraction, then applying business validation to produce a verdict.
- **Current form (main-dev)**: Interactive Streamlit app for manual testing. Headless microservice integration (Kafka/S3/REST callback) is planned but not wired in this branch.
- **Key outcomes**: A per-run artifact folder with `final_result.json`, detailed `manifest.json`, intermediate OCR/LLM outputs, and validation diagnostics.

## 2) High-Level Architecture

- **UI**: `rb-ocr/app.py` (Streamlit). Collects metadata (FIO, reason, doc type), uploads a single file, triggers the pipeline, and presents results with diagnostics.
- **Orchestrator**: `pipeline/orchestrator.py` — single entrypoint `run_pipeline(...)`. Manages stage execution, error handling, timing, and artifact writing.
- **Processors**: `pipeline/processors/*` — OCR filtering, LLM prompts/calls, merge, validation, optional stamp detection.
- **Clients**: `pipeline/clients/*` — Dev OCR gateway (async), internal ForteBank LLM endpoint.
- **Core & Utils**: Shared config, error codes, time/validity helpers, IO utilities, artifact builders, typed DTOs.

## 3) Entry Points

- **User-facing run**: Streamlit
  - Command: `streamlit run rb-ocr/app.py`
  - Calls `run_pipeline(...)` with collected metadata and temp-saved file.
- **Programmatic**: Orchestrator
  - Function: `pipeline.orchestrator.run_pipeline(fio, reason, doc_type, source_file_path, original_filename, content_type, runs_root)`

## 4) Pipeline Stages

All stages operate with a `PipelineContext` that tracks run state, directories, timers, and artifacts. The orchestrator runs stages in order and short-circuits on the first failure.

- **[Acquire]** Save input and basic metadata
  - Save upload into `runs/YYYY-MM-DD/<run_id>/input/original/`.
  - Write `meta/metadata.json` with `{ fio, reason, doc_type }`.
  - If PDF, enforce `MAX_PDF_PAGES=3` pages (configurable).
- **[OCR]** Tesseract Dev OCR (async HTTPX client)
  - Endpoint: `https://dev-ocr.fortebank.com/v2`.
  - Auto-convert images to PDF (Pillow) when needed.
  - Persist `ocr/ocr_response_raw.json` (raw), then derive `ocr/ocr_response_filtered.json` via `filter_ocr_response` to normalized `{ pages: [{page_number, text}] }`.
- **[LLM: Doc-Type Check]**
  - Prompt file: `pipeline/prompts/dtc/v1.prompt.txt`.
  - Save raw LLM response to `llm/doc_type_check.raw.json`.
  - Normalize provider envelope to `llm/doc_type_check.filtered.json`.
  - Validate into DTO `DocTypeCheck`; enforce `single_doc_type==True`.
- **[LLM: Extractor]**
  - Prompt file: `pipeline/prompts/extractor/v1.prompt.txt`.
  - Save raw LLM response to `llm/extractor.raw.json`, then filtered to `llm/extractor.filtered.json`.
  - Validate into DTO `ExtractorResult` requiring `fio` and `doc_date` fields to be strings or null.
- **[Optional: Stamp Detector]** (gated by `STAMP_ENABLED`)
  - External script integration writes `{ "stamp_present": bool }` to `meta/stamp_check_response.json` and copies a visualization image into `input/original` with `_with_boxes` suffix.
- **[Merge]** Curate fields into `llm/merged.json`
  - From extractor: `fio`, `doc_date`.
  - From doc-type checker: `single_doc_type`, `doc_type` (top candidate), `doc_type_known`.
  - Optionally merges `stamp_present` from `stamp_check_response.json`.
  - Build `meta/side_by_side.json` for quick manual QA.
- **[Validate & Finalize]**
  - Compute checks and verdict and write `validation/validation.json`.
  - Produce `meta/final_result.json` and `meta/manifest.json` with timings and curated artifact paths.

## 5) Run and Artifact Layout

- **Root** (`pipeline/core/settings.py`): `RUNS_DIR`
  - Default: `<repo>/rb-ocr/runs` (auto-created). Override via env `RB_IDP_RUNS_DIR`.
- **Per-run structure** (`run_id` = `YYYYMMDD_HHMMSS_<5-hex>`):
  - `runs/YYYY-MM-DD/<run_id>/`
    - `input/original/` — saved input file and optional `_with_boxes` visualization
    - `ocr/` — `ocr_response_raw.json`, `ocr_response_filtered.json`
    - `llm/` — `doc_type_check.raw.json`, `doc_type_check.filtered.json`, `extractor.raw.json`, `extractor.filtered.json`, `merged.json`
    - `meta/` — `metadata.json`, `manifest.json`, `final_result.json`, `side_by_side.json`, `stamp_check_response.json` (if enabled)
    - `validation/` — `validation.json`

## 6) External Integrations

- **Dev OCR (Tesseract gateway)** — `pipeline/clients/tesseract_async_client.py`
  - Uploads PDF to `/v2/pdf`, polls `/v2/result/{id}`.
  - Timeouts: client ~60s; overall wait default 300s with 2s poll.
  - Image inputs auto-converted to PDF via Pillow. MIME detection by `mimetypes`.
- **Internal LLM endpoint (DMZ)** — `pipeline/clients/llm_client.py`
  - URL: `https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2`.
  - Returns OpenAI-like envelope; SSL verification is disabled deliberately for dev (must be fixed for prod).
  - `filter_llm_generic_response` normalizes raw strings/JSONL/envelopes to a single dict.
- **Stamp Detector (optional)** — `pipeline/processors/stamp_check.py`
  - Wraps external script with hardcoded dev paths (should be moved to config/env for production):
    - `DETECTOR_PY`, `DETECTOR_SCRIPT`, `DETECTOR_WEIGHT`.
  - PDFs are rendered to a tall JPEG via PyMuPDF, then detection runs.

## 7) Validation Logic and Verdict

- Implemented in `pipeline/processors/validator.py`.
- **Checks**
  - `fio_match` — deterministic variant matching with initials tolerance and fuzzy fallback (RapidFuzz/SequenceMatcher). Diagnostics include matched variant and scores.
  - `doc_type_known` — whether doc-type checker recognized type.
  - `doc_date_valid` — based on per-type validity policy (see below).
  - `single_doc_type_valid` — true only if classifier asserted a single doc type.
  - `stamp_present` — tri-state; only considered if `STAMP_ENABLED`.
- **Verdict rule**
  - `True` only if: `fio_match && doc_type_known && doc_date_valid && single_doc_type_valid && (stamp_present if enabled)`.
- **Date parsing**: supports `DD.MM.YYYY`, `YYYY-MM-DD`, `DD/MM/YYYY`.
- **Validity policy** (`pipeline/core/validity.py`)
  - Default: 40 days from document date.
  - Overrides (days):
    - «Заключение ВКК» — 180
    - «Справка об инвалидности» — 360
    - «Справка о степени утраты общей трудоспособности» — 360
    - «Приказ о выходе в декретный отпуск по уходу за ребенком» — 365
    - «Справка о выходе в декретный отпуск по уходу за ребенком» — 365

## 8) Configuration and Flags

- **File names and limits** (`pipeline/core/config.py`)
  - Filenames: `OCR_RAW`, `OCR_PAGES`, `LLM_DOC_TYPE_RAW`, `LLM_DOC_TYPE_FILTERED`, `LLM_EXTRACTOR_RAW`, `LLM_EXTRACTOR_FILTERED`, `MERGED_FILENAME`, `VALIDATION_FILENAME`, `METADATA_FILENAME`.
  - Limits: `MAX_PDF_PAGES=3`.
  - Timezone offset: `UTC_OFFSET_HOURS=5`.
  - Feature flag: `STAMP_ENABLED = env(RB_IDP_STAMP_ENABLED)` (default: off).
- **Runs dir** (`pipeline/core/settings.py`)
  - Override with `RB_IDP_RUNS_DIR`.

## 9) Error Handling and Codes

- Centralized codes/messages in `pipeline/core/errors.py` (RU messages). Examples:
  - **Acquisition/UI**: `PDF_TOO_MANY_PAGES`, `FILE_SAVE_FAILED`
  - **OCR**: `OCR_FAILED`, `OCR_FILTER_FAILED`, `OCR_EMPTY_PAGES`
  - **Doc-type**: `DTC_FAILED`, `MULTIPLE_DOCUMENTS`, `DTC_PARSE_ERROR`
  - **Extractor**: `EXTRACT_FAILED`, `LLM_FILTER_PARSE_ERROR`, `EXTRACT_SCHEMA_INVALID`
  - **Merge/Validation**: `MERGE_FAILED`, `VALIDATION_FAILED`, `UNKNOWN_ERROR`
  - **Check-derived**: `FIO_MISMATCH`, `FIO_MISSING`, `DOC_TYPE_UNKNOWN`, `DOC_DATE_TOO_OLD`, `DOC_DATE_MISSING`, `SINGLE_DOC_TYPE_INVALID`
  - **Stamp**: `STAMP_NOT_PRESENT`, `STAMP_CHECK_MISSING`
- **Failure path**
  - `fail_and_finalize(code, details, ctx)` writes `final_result.json` with `verdict=false` and a curated error code list, plus `manifest.json` with status `error`.
- **Success path**
  - `finalize_success(verdict, checks, ctx)` writes `final_result.json` and `manifest.json` with status `success`.

## 10) Timings and SLA

- **Timers**: `pipeline/utils/timing.py` accumulates seconds per stage via context managers.
- **Manifest timing**: `manifest.json.timing` contains `duration_seconds`, `ocr_seconds`, `llm_seconds`, and `stamp_seconds` (if enabled).
- **UI display**: Streamlit shows these metrics and expands diagnostics (`final_result.json`, `side_by_side.json`).

## 11) Streamlit UI specifics

- Collects `fio`, `reason`, and constrained `doc_type` (linked choices by reason map) and the file.
- Writes temporary upload, calls `run_pipeline`, and renders:
  - Verdict (True/False) and human-readable error messages (mapped from codes).
  - Diagnostics: `final_result.json`, optional `side_by_side.json` table.
  - Optional stamp visualization from `input/original/*_with_boxes.*`.

## 12) Data Contracts (internal artifacts)

- **final_result.json** (curated public output)
```json
{
  "run_id": "20250101_123456_ab123",
  "verdict": true,
  "errors": [
    { "code": "..." }
  ]
}
```
- **manifest.json** (operator/debug)
```json
{
  "run_id": "...",
  "created_at": "DD.MM.YYYY",
  "timing": {
    "duration_seconds": 1.23,
    "stamp_seconds": null,
    "ocr_seconds": 0.85,
    "llm_seconds": 0.60
  },
  "user_input": {"fio": "...", "reason": "...", "doc_type": "..."},
  "file": {"original_filename": "x.pdf", "saved_path": "...", "content_type": "...", "size_bytes": 12345},
  "artifacts": {
    "final_result_path": ".../meta/final_result.json",
    "side_by_side_path": ".../meta/side_by_side.json",
    "merged_path": ".../llm/merged.json"
  },
  "status": "success",
  "error": null
}
```
- **side_by_side.json** (manual QA)
```json
{
  "request_created_at": "DD.MM.YYYY",
  "fio": {"meta": "...", "extracted": "..."},
  "doc_type": {"meta": "...", "extracted": "..."},
  "doc_date": {"extracted": "YYYY-MM-DD", "valid_until": "DD.MM.YYYY"},
  "single_doc_type": {"extracted": true},
  "doc_type_known": {"extracted": true},
  "stamp_present": {"extracted": true}
}
```

## 13) Packages and Dependencies (used in code)

- `streamlit`, `httpx`, `urllib.request`/`ssl`, `pydantic` (optional fallback provided), `rapidfuzz` (optional, else `difflib`), `pypdf`/`PyPDF2` (optional), `Pillow` (image→PDF), `PyMuPDF` (PDF rendering for stamp stage), `json`, `re`, `pathlib`.

## 14) Security and Compliance Notes

- LLM dev endpoint currently ignores SSL verification (dev only). Must enforce proper TLS in production.
- Stamp detector paths are hardcoded to an absolute dev location. Externalize into config/env and secure access to weights.
- PII (FIO) is processed; ensure data retention policies, redaction in logs, and encryption at rest for stored artifacts when moving to prod.

## 15) Roadmap for Event-Driven Bank Integration

Planned integration, aligning with the microservice analysis in `idp-loan-deferment-architecture-analysis.md`:

- **Ingestion**: Kafka topic `di-loan-delay.event.docs-uploaded` (schema to confirm). Generate `run_id`, validate payload.
- **Fetch**: MinIO/S3 (`s3-dev.fortebank.com:9443`) download by `s3_path` (bucket `loan-statements-dev` in dev; to confirm contract).
- **Process**: Reuse `run_pipeline(...)` in a headless worker; persist artifacts keyed by `(request_id, run_id)`.
- **Callback**: POST verdict to bank REST endpoint with idempotency and retries.
- **Resilience**: At-least-once, DLQ, timeouts/backoff, idempotency keys.
- **Observability**: Structured logs, metrics, and trace IDs correlating `request_id` and `run_id`.

## 16) Configuration Summary

- **Env flags**
  - `RB_IDP_RUNS_DIR` — override runs root.
  - `RB_IDP_STAMP_ENABLED` — enable stamp stage and related checks.
- **Constants**
  - `MAX_PDF_PAGES=3`, `UTC_OFFSET_HOURS=5`.

## 17) Known Limitations (dev)

- SSL verification disabled for LLM dev endpoint.
- Stamp detector uses absolute paths and is optional by feature flag.
- `final_result.json` intentionally contains only error codes (messages resolved in UI).
- Some libraries are optional; functionality degrades gracefully if absent (e.g., PDF page count).

## 18) Glossary of Key Modules

- **orchestrator**: `pipeline/orchestrator.py` — stages, timing, artifacts, error handling.
- **clients**: `tesseract_async_client.py`, `llm_client.py` — OCR/LLM integrations.
- **processors**: `filter_ocr_response.py`, `agent_doc_type_checker.py`, `agent_extractor.py`, `merge_outputs.py`, `validator.py`, `stamp_check.py`.
- **core**: `config.py`, `settings.py`, `errors.py`, `validity.py`, `dates.py`.
- **utils**: `io_utils.py`, `artifacts.py`, `timing.py`.
- **models**: `models/dto.py` — typed DTOs for doc-type and extractor outputs.

---

# Appendix A — Error Codes (RU messages)

- Acquisition/UI: PDF_TOO_MANY_PAGES, FILE_SAVE_FAILED
- OCR: OCR_FAILED, OCR_FILTER_FAILED, OCR_EMPTY_PAGES
- Doc-type: DTC_FAILED, MULTIPLE_DOCUMENTS, DTC_PARSE_ERROR
- Extractor: EXTRACT_FAILED, LLM_FILTER_PARSE_ERROR, EXTRACT_SCHEMA_INVALID
- Merge/Validation: MERGE_FAILED, VALIDATION_FAILED, UNKNOWN_ERROR
- Check-derived: FIO_MISMATCH, FIO_MISSING, DOC_TYPE_UNKNOWN, DOC_DATE_TOO_OLD, DOC_DATE_MISSING, SINGLE_DOC_TYPE_INVALID
- Stamp: STAMP_NOT_PRESENT, STAMP_CHECK_MISSING

# Appendix B — Document Validity Windows

- Default: 40 days from `doc_date`.
- Overrides:
  - Заключение ВКК — 180
  - Справка об инвалидности — 360
  - Справка о степени утраты общей трудоспособности — 360
  - Приказ о выходе в декретный отпуск по уходу за ребенком — 365
  - Справка о выходе в декретный отпуск по уходу за ребенком — 365
