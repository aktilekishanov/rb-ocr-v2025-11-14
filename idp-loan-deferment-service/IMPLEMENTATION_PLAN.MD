# Implementation Plan — IDP Loan Deferment FastAPI Service (Standalone)

Goal: deliver an independent FastAPI service with async endpoints that execute the RB IDP pipeline and return the same `final_result.json` body as the current main-dev MVP.


## Open Questions — Resolved
- HTTP response body **must be exactly** the file content of `final_result.json` (no extra internal fields such as `final_result_path`).
- We **do not include** `stamp_present` in `final_result.json` at all, even if stamp check is enabled.
- We **keep only the asynchronous** API: background jobs (`POST /v1/jobs`, `GET /v1/jobs/{run_id}`) and related endpoints; the synchronous `POST /v1/process` endpoint is **not** part of the target API.
- Storage layout will **keep the current IDP layout** (e.g., `runs/YYYY-MM-DD/<run_id>/input`), and we **do not** change it to the main-dev `input/original` layout.


## Final target API and schemas
- POST /v1/jobs
  - Inputs: `file`, `fio` (and optional meta fields)
  - Response 202: `{ "run_id": str, "status": "accepted" }`
  - Background task runs pipeline and writes artifacts (including any internal `final_result.json` if we keep it), and updates job status.
- GET /v1/jobs/{run_id}
  - Response 200 schema (single canonical contract for status + result):
    - `{ "run_id": str, "status": "accepted"|"running"|"completed"|"failed", "verdict"?: bool, "errors"?: ["ERROR_CODE"] }`
    - `verdict` and `errors` are populated only when the job has reached a terminal state (e.g. `completed` or `failed`).


## What “same final_result.json” means (from main-dev)
- File schema on disk built in main-dev by `build_final_result` (internal reference):
  - `{"run_id": str, "verdict": bool, "errors": [{"code": str}]}`
  
For this IDP service, we reuse the same base schema **internally** (e.g. for an internal `final_result.json` artifact), still without `stamp_present`. The public HTTP contract is simplified to `{run_id, status, verdict?, errors?}` exposed via `GET /v1/jobs/{run_id}`.


## Current state summary
- main-dev
  - Stage-based orchestrator writes artifacts and `final_result.json` via `pipeline/utils/artifacts.py`.
- idp-loan-deferment-service (draft)
  - Solid FastAPI skeleton with health, process, jobs, metrics, tracing.
  - Domain pipeline skeleton with stages: acquire → ocr → doc_type → extract → merge → validate.
  - `application/services/pipeline_runner.py` writes a minimal `final_result.json` but with `errors: list[str]` (needs alignment to list of objects with `code`).
  - LocalDiskStorageAdapter already writes `runs/YYYY-MM-DD/<run_id>/{input,meta,...}`.


## Implementation steps
1) Schema and response alignment
- Define a `JobStatus` / `JobResult` Pydantic model for the public API: `run_id: str`, `status: Literal["accepted","running","completed","failed"]`, optional `verdict: bool | None`, optional `errors: list[str] | None`.
- Optionally (internal), keep `FinalResult` model mirroring the main-dev file shape: `run_id: str`, `verdict: bool`, `errors: list[ErrorCode]`.
- Add conversion helper(s) from internal domain result (`RunResult`) to:
  - internal `FinalResult` (if used), and
  - external `JobStatus` payload (`verdict` + `errors: list[str]`).

2) Pipeline runner bridge returns correct shape
- Update the pipeline runner used by async jobs to:
  - Produce a single internal result object (and optionally persist an internal `final_result.json`).
  - Update job metadata so that `GET /v1/jobs/{run_id}` can always derive `{run_id, status, verdict?, errors?}` from storage.

3) Route adjustments (async-only API)
- Ensure `POST /v1/jobs` accepts the file + meta, enqueues the pipeline, and returns `{ "run_id": str, "status": "accepted" }`.
- Ensure `GET /v1/jobs/{run_id}` exposes job status and the final verdict + error codes when available, using the agreed schema.

4) Storage alignment
- Keep LocalDiskStorageAdapter writing to the current IDP layout `runs/YYYY-MM-DD/<run_id>/{input,meta,...}`. Any `final_result.json` written to `meta/` is an internal artifact; the public API always reads from the job metadata to build the `{run_id,status,verdict?,errors?}` response.

5) Domain pipeline parity with main-dev checks (incremental)
- Validate stage should compute the same checks as main-dev:
  - FIO match, doc_type_known, doc_date validity, single_doc_type_valid.
- Plan to port or reimplement equivalent rules:
  - Bring over `compute_valid_until` logic and date parsing rules.

6) OCR and LLM clients
- Wire `OcrHttpClient` to Forte OCR v2 API and `CompletionsHttpClient` for LLM; provide timeouts, retries/backoff, and circuit-breaker-friendly patterns.
- For dev mode (no URLs configured), keep internal fakes (already present) so local runs work without external services.

7) Error taxonomy and HTTP errors
- Keep domain error codes simple (string identifiers). Map HTTP layer errors via `to_http_error` as today.
- Ensure persistence-layer `final_result.json` contains only `{code}` objects, not messages.

8) Observability
- Reuse existing `RequestIdMiddleware`, Prometheus metrics (/metrics), and optional OpenTelemetry tracing hooks.
- Add metrics for pipeline duration and per-stage durations, following main-dev’s `StageTimers` idea (you already have placeholders in observability/metrics.py).

9) Concurrency and performance
- Use FastAPI async endpoints and `anyio.to_thread.run_sync` for blocking file IO (copy, OCR sync calls if any).
- Limit payload size and number of concurrent jobs (basic in-memory throttling can be added if needed).

10) Testing
- Unit tests for:
  - Mapping from domain `RunResult` to public `JobStatus` schema (`verdict` + error codes).
  - Validation checks parity with main-dev on golden inputs.
- Integration tests:
  - `POST /v1/jobs` → background finish → `GET /v1/jobs/{run_id}`.
  - Contract tests vs main-dev outputs for a small set of golden PDFs (compare verdict + error codes).

11) Deployment readiness
- Dockerfile present; ensure `uvicorn` workers count tuned (e.g., `--workers N`, `--loop uvloop`).
- Provide `.env.example` with IDP_ variables. Document min resources.


## Work breakdown (WBS)
- W1: Schema alignment and helpers (JobStatus model, optional internal FinalResult, error mapping)
- W2: Pipeline bridge update for async jobs and job metadata persistence
- W3: Jobs flow ensures correct status transitions and final verdict exposure via `GET /v1/jobs/{run_id}`
- W4: Verify and document current IDP storage layout usage (`runs/YYYY-MM-DD/<run_id>/{input,meta,...}`)
- W5: Port validation rules parity (doc date validity, doc type known, FIO match)
- W6: Wire real OCR/LLM clients, timeouts/retries; keep fakes for dev
- W7: Tests (unit/integration/contract) and fixtures; golden output comparisons
- W8: Observability polish; metrics for durations and outcomes
- W9: Docs and runbook updates; readiness checks


## Acceptance criteria
- `GET /v1/jobs/{run_id}` returns a JSON body that matches the agreed schema: `{run_id, status, verdict?, errors?}`.
- When a job is `completed` (or terminal), `verdict` and `errors` in `GET /v1/jobs/{run_id}` match the internally computed result (and any internal `final_result.json`, if present).
- Background jobs are retrievable via `GET /v1/jobs/{run_id}` and reach `completed` with the expected verdict + error codes for golden cases.
- For a curated sample set, responses from `GET /v1/jobs/{run_id}` match main-dev outputs (verdict + error codes) under identical inputs.
- Endpoints are async-safe, and service starts with health/ready ok. Basic load test shows stability with concurrent jobs.


## Timeline (fast-track)
- Day 1: W1–W2
- Day 2: W3–W4
- Day 3: W5 (parity rules) + unit tests
- Day 4: W6–W7 (integration/contract tests)
- Day 5: W8–W9 and buffer


## Rollout
- Ship behind environment flag(s) for external clients. Keep dev fakes default.
- No storage migration required; we keep the existing IDP layout. Document that `GET /v1/jobs/{run_id}` is the single public contract for status + result.
