# RB Loan Deferment IDP — FastAPI Service (From Scratch) Phased Implementation Plan

Audience: non‑backend stakeholders and engineers ramping up on backend. This plan explains what we will build, why, and how we will deliver it step by step. No code changes are made by this document.

## 0) What we are building (in plain words)

- **Goal**: Build a **new, standalone FastAPI web service** for loan deferment documents. It does **not** import or depend on `apps/main-dev`; it reimplements the needed logic inside its own project.
- **How it works**: A caller sends a document (PDF/JPEG) with required FIO (full name), which the pipeline later uses for validation. Our service runs OCR + AI extraction + checks and returns a **verdict** (pass/fail). Internally we keep artifacts and logs on disk for audit.
- **Why FastAPI**: It’s a modern Python framework that is fast, well‑documented, supports async (great for calling OCR/LLM), and auto‑generates API docs.
- **Storage now**: We keep using the **local file system** for run artifacts (simple to start). We design it so we can later switch to MinIO/S3 with minimal changes.

## 1) Big picture (end‑to‑end flow)

1) Client calls our API with a document and metadata.
2) Service saves the file into a new "run" folder and orchestrates steps: OCR → LLM → merge → validation.
3) Service returns a simple JSON with **run UUID**, **verdict**, and **errors []**.
4) Operators/tech team can review logs and artifacts on disk if something goes wrong (artifacts are internal, not returned to business systems).

```
Client ─► FastAPI (HTTP) ─► Orchestrator (stages) ─► Artifacts on disk
                          └► Result (JSON) ◄───────┘
```

## 2) Project layout (new directory)

- **Directory**: `apps/idp-loan-deferment-service`
- **Proposed structure (no code yet)**:
```
apps/idp-loan-deferment-service/
  README.md
  REPORT_3.MD   # this document
  app/
    main.py                 # FastAPI app startup (uvicorn); defines the ASGI app
    api/
      v1/
        routes_process.py   # /v1/process (sync)
        routes_jobs.py      # /v1/jobs (async submit+status)
        routes_health.py    # /health, /ready
    models/
      schemas.py            # Request/response pydantic models
    services/
      pipeline_runner.py    # Implements the orchestration logic (acquire → OCR → LLM → merge → validate)
      storage/
        base.py             # Storage interface (local now, S3 later)
        local_disk.py       # Local filesystem implementation
      clients/
        ocr_client.py       # Async OCR wrapper (httpx)
        llm_client.py       # Async LLM client (httpx)
    core/
      config.py             # Env config (paths, flags, timeouts)
      logging.py            # Structured logging, correlation IDs
      errors.py             # API error mapping
  tests/
    test_smoke.py
  requirements.txt
  Dockerfile
```

- **Important principle**: everything uses an interface to write/read artifacts (local now; MinIO/S3 later) so we don’t rewrite business logic when we scale out.

## 3) Phased delivery

### Phase 0 — Foundations
- **Deliverables**
  - **App skeleton**: FastAPI app with `/health` and `/ready`.
  - **Config**: `.env` support or environment variables for paths and timeouts.
  - **Logging**: request IDs in logs; JSON logs for easy parsing.
- **Success criteria**: Service runs locally via `uvicorn app.main:app --reload`.

### Phase 1 — Sync processing (MVP API)
- **Endpoints**
  - **POST `/v1/process`**: Receives multipart upload (file) and a required `fio` field. Returns a simple JSON with `run_id`, `verdict`, and `errors`.
  - **GET `/health`, `/ready`**: Return service status.
- **Behavior**
  - Implements the orchestration logic **inside this service** (acquire → OCR → LLM → merge → validate), conceptually similar to the prototype but with independent code.
  - Artifacts are written to local disk under `runs/YYYY-MM-DD/<run_id>/...` for internal audit and troubleshooting only.
- **Success criteria**: Single request processes in under the agreed budget for normal docs; verdict and errors are returned; operators can inspect artifacts on disk when needed.

### Phase 2 — Async jobs (better UX under load)
- **Endpoints**
  - **POST `/v1/jobs`**: Accepts the same inputs as `/v1/process` but returns quickly with `{ run_id, status: "accepted" }`.
  - **GET `/v1/jobs/{run_id}`**: Returns job `status`, `verdict` (when done), and `errors`.
- **Implementation options**
  - Start with **FastAPI BackgroundTasks** (simple) → upgrade later to **Celery + Redis** for reliability and retries.
- **Success criteria**: Multiple jobs can be in flight; API remains responsive; job status is trackable.

### Phase 3 — Observability & resilience
- **Add**
  - **Metrics**: per‑stage timings, success/fail counters.
  - **Tracing**: instrument OCR/LLM calls, surface latencies.
  - **Error mapping**: stable error codes to clean API responses.
  - **Timeouts/retries**: for OCR/LLM and storage I/O, with exponential backoff.
- **Success criteria**: We can see performance and errors in dashboards; transient faults are auto‑retried.

### Phase 4 — Security hardening
- **Add**
  - **TLS** termination (or run behind a gateway that enforces TLS).
  - **Auth**: OAuth/JWT or mTLS for client calls.
  - **Secrets**: from env/secret store; no hardcoded paths/keys.
  - **PII handling**: define retention and redaction policies.
- **Success criteria**: Security review passes; secrets and certificates are managed safely.

### Phase 5 — Packaging & deployment
- **Add**
  - **Dockerfile** with multi‑stage build.
  - **Run command**: `gunicorn -k uvicorn.workers.UvicornWorker -w 2 app.main:app`.
  - **Kubernetes (optional)**: liveness/readiness probes, HPA; or VM systemd service.
- **Success criteria**: Service runs in the target environment with logs, metrics, and health endpoints.

### Phase 6 — (Optional later) Event‑driven + external storage
- **Kafka ingestion**: consumer that submits jobs to the same pipeline.
- **MinIO/S3 storage**: swap the storage implementation behind `storage/base.py` with minimal code changes.
- **Callback**: POST verdict to bank endpoint when jobs complete.

## 4) API contracts (easy to read)

- **POST `/v1/process`** (sync)
  - **Request**: multipart/form-data with fields
    - `file` (PDF/JPG/PNG)
    - `fio` (string, required; used by validation logic)
  - **Response** (example)
```json
{
  "run_id": "20251231_235959_ab123",
  "verdict": true,
  "errors": []
}
```

- **POST `/v1/jobs`** (async)
  - **Response**: `{ "run_id": "...", "status": "accepted" }`
- **GET `/v1/jobs/{run_id}`** (status)
  - **Response**: `{ "status": "running|completed|failed", "verdict": true|false|null, "errors": [ ... ] }`

## 5) Non‑functional requirements (NFRs)

- **Performance**: P95 latency target for typical docs (to be agreed). Timeouts for OCR/LLM with retries.
- **Reliability**: Clear error codes; no crashes on malformed files; graceful shutdown.
- **Scalability**: Stateless API. Local disk for now; abstracted to allow MinIO later.
- **Observability**: JSON logs, metrics, and correlation IDs.
- **Security**: TLS and auth when exposed outside the lab; secrets managed via env/VAULT.

## 6) Risks and mitigations

- **LLM/OCR slow or flaky**
  - Mitigate with timeouts, retries, circuit breakers, and queues (Phase 2+).
- **Local disk limits**
  - Monitor space; add cleanup policies; plan S3/MinIO migration.
- **Name mismatches (FIO) and dates**
  - Keep deterministic + fuzzy matching; log diagnostics for reviewers.

## 7) Environment variables (examples)

- **Paths & flags**
  - `RB_IDP_RUNS_DIR=/var/app/runs`
  - `RB_IDP_STAMP_ENABLED=false`
- **Clients**
  - `OCR_BASE_URL=https://dev-ocr.fortebank.com/v2`
  - `LLM_BASE_URL=https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2`
  - `HTTP_TIMEOUT_SECONDS=60`

## 8) Testing strategy (simple and clear)

- **Unit tests**: models, small helpers, error mapping.
- **Integration tests**: hit `/v1/process` with sample PDFs/images; assert verdict and artifacts exist.
- **Load test (lightweight)**: 5–10 parallel requests, observe timings and errors.
- **Manual QA**: read `manifest.json`, `final_result.json`, and `side_by_side.json` for correctness.

## 9) Acceptance criteria per phase

- **Phase 0**: Service boots; health endpoints OK.
- **Phase 1**: `/v1/process` returns a valid result and artifacts for sample docs.
- **Phase 2**: `/v1/jobs` + `/v1/jobs/{id}` work for multiple concurrent jobs.
- **Phase 3**: Metrics and structured logs available; retries in place.
- **Phase 4**: Security posture reviewed; secrets not hardcoded.
- **Phase 5**: Built and deployed in target environment.

## 10) Roles and responsibilities

- **Backend engineer**: APIs, services, storage abstraction.
- **MLOps/AI engineer**: OCR/LLM config, prompts, and performance tuning.
- **DevOps**: Deployments, monitoring, certificates, secrets, persistence.
- **QA**: Test plans, sample docs, regression suites.

## 11) Glossary (plain language)

- **API**: A web endpoint that programs call.
- **Async**: Handling multiple calls at once without waiting for each step to finish, improving speed.
- **Artifact**: Files we save during processing (inputs, outputs, logs).
- **Orchestrator**: The code that runs steps in order (OCR → AI → checks).
- **Verdict**: Final pass/fail outcome after checks.

---

### TL;DR
- We start a new FastAPI service in `apps/idp-loan-deferment-service`.
- Phase by phase: skeleton → sync `/v1/process` → async jobs → observability → security → deploy.
- Local disk now, clean abstraction to move to MinIO/S3 later, with no rewrite of business logic.
