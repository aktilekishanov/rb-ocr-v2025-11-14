# Uploaded File Journey

This document describes the lifecycle of a file uploaded to the RB-OCR system, based on the current codebase (as of Dec 2025).

## 1. Ingestion (Entry Point)

The journey begins when a user uploads a file via the UI or an external system sends a request to the API.

*   **UI**: The Streamlit app (`apps/ui/app.py`) accepts the file and sends it to the FastAPI backend.
*   **API**: The FastAPI service (`apps/fastapi-service/main.py`) receives the file at `POST /v1/verify`.

## 2. Temporary Storage (FastAPI)

Upon receipt, the FastAPI service immediately saves the file to a temporary location on the server's filesystem.

*   **Location**: System temporary directory (e.g., `/tmp/tmp<random>_<filename>`).
*   **Purpose**: To hold the file in memory/disk while the processing pipeline is initialized.
*   **Lifecycle**:
    *   **Created**: At the start of the request.
    *   **Deleted**: Automatically deleted in the `finally` block of the request handler, regardless of success or failure.

## 3. Persistent Storage (Pipeline)

The pipeline orchestrator (`apps/fastapi-service/pipeline/orchestrator.py`) creates a permanent record of the run.

*   **Run ID**: A unique ID is generated (e.g., `20251203_120000_abc12`).
*   **Directory Structure**: A dedicated directory is created: `runs/{date}/{run_id}/`.
*   **File Copy**: The temporary file is **copied** to:
    `runs/{date}/{run_id}/input/original/{filename}`
*   **Persistence**: This copy **remains on disk** indefinitely in the current implementation. It is NOT deleted after processing.

## 4. Processing Artifacts

As the file moves through the pipeline, several intermediate files are generated and stored in the `runs/{date}/{run_id}/` directory:

| Stage | Artifacts Created | Location | Deleted? |
| :--- | :--- | :--- | :--- |
| **OCR** | OCR Results (JSON) | `ocr/` | **No** |
| **Doc Type** | Raw LLM Response | `llm/doc_type_raw.txt` | **No** |
| **Doc Type** | Filtered JSON | `llm/doc_type_filtered.json` | **No** |
| **Extract** | Raw LLM Response | `llm/extractor_raw.txt` | **Yes** (Explicitly deleted) |
| **Extract** | Filtered JSON | `llm/extractor_filtered.json` | **No** |
| **Merge** | Merged Data | `llm/merged.json` | **No** |
| **Validation** | Validation Results | `validation/validation.json` | **No** |
| **Finalize** | Final Result & Manifest | `meta/` | **No** |

## 5. Cleanup & Retention

*   **Current State**:
    *   The **initial temp file** in `/tmp` is deleted immediately.
    *   The **copied file** in `runs/.../input/original` is **NEVER deleted** by the application code.
    *   The `runs` directory will grow indefinitely unless manually cleaned.
    *   There is **no automated cron job** or background task currently implemented in the code to clean up old runs.

*   **Planned Strategy** (from `FILE_RETENTION_STRATEGY.md`):
    *   **Retention Period**: 30 days.
    *   **Mechanism**: A proposed cron job to delete files older than 30 days.
    *   **Database**: Metadata should be retained in the database even after the physical file is deleted.

## 6. Database Integration

*   **Current State**: The pipeline currently writes results to **JSON files** (`final_result.json`, `manifest.json`). It does **not** appear to write to a PostgreSQL database in the current `orchestrator.py` implementation.
*   **Planned State** (from `DB_SCHEMA.md`):
    *   A `verification_runs` table is designed to store metadata, file paths, and results.
    *   This integration is documented but not yet fully active in the main pipeline code.

## Summary

| File Instance | Location | Lifecycle |
| :--- | :--- | :--- |
| **Upload Stream** | Memory | Consumed immediately |
| **Temp File** | `/tmp/...` | Deleted after request |
| **Archive Copy** | `runs/.../input/original/` | **Kept Indefinitely** (Current) |
| **Metadata** | `runs/.../meta/` | **Kept Indefinitely** (Current) |
