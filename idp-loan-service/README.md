# idp-loan-service

Minimal FastAPI wrapper around the main-dev RB-OCR pipeline.

## Endpoints

- POST /v1/jobs
  - multipart/form-data: file (pdf/jpg/png), fio (string)
  - Returns 202: { job_id, status: "queued" }
- GET /v1/jobs/{job_id}
  - queued/running: { job_id, status, verdict: null, errors: [] }
  - completed: { job_id, status: "completed", verdict: bool, errors: [{code}] }
  - error: { job_id, status: "error", verdict: false, errors: [{code:"INTERNAL_ERROR"}] }

## How to run

```bash
pip install -r apps/idp-loan-service/requirements.txt
# Run from repo root using --app-dir because the folder name contains a dash
uvicorn main:app --host 0.0.0.0 --port 8000 --app-dir apps/idp-loan-service
```

If running from repository root, no extra PYTHONPATH is required: the app adjusts `sys.path` automatically to load `pipeline.*` from `apps/main-dev/rb-ocr`.

## Notes
- Uses main-dev pipeline with OCR v2 base URL hardcoded in the client.
- Feature flag RB_IDP_STAMP_ENABLED=false by default (no stamp check).
- Artifacts are written under pipeline RUNS_DIR (env override: RB_IDP_RUNS_DIR).
- Minimal persistence: <RUNS_DIR>/jobs_index.json for completed/error jobs.
- For image uploads, Pillow is required for image->PDF conversion; included via requirements.
