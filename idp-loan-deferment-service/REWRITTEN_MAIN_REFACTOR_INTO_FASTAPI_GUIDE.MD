# Main‑dev → Standalone FastAPI Service (Better by Design) – Refactor Guide

Purpose: rebuild main‑dev as a clean, modular, independent FastAPI service under `apps/idp-loan-deferment-service` – not by copy/paste, but by redesigning for clarity, testability, and operability.

This guide proposes a modern architecture (hexagonal/clean architecture), precise folders, contracts, and a phased migration plan with acceptance criteria.

---

## 1) Architecture principles (non‑negotiables)

- **Separation of concerns**: application (use‑cases), domain (pipeline logic), infrastructure (clients, storage), interface (FastAPI).
- **Pure core**: pipeline stages are pure/side‑effect‑free functions where possible; IO is in adapters.
- **Dependency rule**: inner layers know nothing about outer layers. Infra depends on domain; not vice versa.
- **Contracts first**: explicit interfaces for storage and external clients. Swappable implementations (local → S3/MinIO; mock clients for tests).
- **Async ready**: httpx clients, graceful timeouts/retries, cancellation‑safe.
- **Observability**: structured logs, metrics, error codes, optional tracing.
- **Versioned APIs**: `/v1/...` now, keep backward‑compatible responses.

---

## 2) Target directory layout

Inside `apps/idp-loan-deferment-service/app/`:

- `api/`
  - `v1/`
    - `routes_health.py` – health/ready
    - `routes_process.py` – POST `/v1/process`
    - `routes_jobs.py` – POST `/v1/jobs`, GET `/v1/jobs/{id}`
  - `schemas.py` – Pydantic request/response models
- `application/` (use‑cases and orchestration)
  - `usecases/`
    - `process_document.py` – orchestrates one sync request (calls domain pipeline through ports)
    - `submit_job.py`, `get_job_status.py` – async job flows
  - `services/`
    - `jobs.py` – job lifecycle (in‑mem + persisted status)
    - `pipeline_runner.py` – bridges API → domain.run_pipeline, measures duration
- `domain/` (pure logic & ports)
  - `pipeline/`
    - `orchestrator.py` – run_pipeline(...) with stages (no HTTP, no file IO directly)
    - `stages/` – `acquire.py`, `ocr.py`, `doc_type_check.py`, `extract.py`, `merge.py`, `validate.py`
    - `models.py` – Pydantic models (DocTypeCheck, ExtractorResult, ValidationResult)
    - `constants.py` – file names and limits
    - `errors.py` – domain error codes
  - `ports/` – interfaces (protocols)
    - `storage_port.py` – save/read artifacts, manifests, inputs
    - `ocr_port.py` – upload/wait/get OCR results
    - `llm_port.py` – ask LLM
- `infrastructure/` (adapters to real world)
  - `storage/`
    - `local_disk.py` – implements `StoragePort`
    - `s3_minio.py` (later) – implements `StoragePort`
  - `clients/`
    - `ocr_http.py` – httpx client implements `OCRPort`
    - `llm_http.py` – httpx client implements `LLMPort`
  - `retrying.py` – retry helpers (sync/async)
- `core/`
  - `config.py` – Pydantic Settings (OCR/LLM URLs, timeouts, flags)
  - `logging.py` – request‑id middleware & logger
- `observability/`
  - `metrics.py` – counters/histograms, middleware, `/metrics`
  - `errors.py` – API error mapping (stable codes)
  - `tracing.py` – optional OTel init/instrumentation
- `main.py` – FastAPI app factory, lifespan; registers middleware/routers

Tests under `apps/idp-loan-deferment-service/tests/` mirror the structure.

Why this layout?
- Domain code is framework‑agnostic and testable in isolation.
- External systems are behind ports (interfaces), enabling mocks and future swaps.
- Application layer composes ports and orchestrates use‑cases.

---

## 3) Contracts (ports) – define first

- `StoragePort`
  - `save_input(run_id, src_path) -> Path`
  - `write_json(run_id, rel_path, obj) -> Path`
  - `read_json(run_id, rel_path) -> dict`
  - `ensure_dirs(run_id, *rel_dirs)`
- `OCRPort`
  - `upload(pdf_path) -> {id, ...}`
  - `wait_result(id, timeout, interval) -> {success, result|error, raw}`
- `LLMPort`
  - `classify_doc_type(pages_obj) -> str/json`
  - `extract_fields(pages_obj) -> str/json`

All domain stages accept a `ctx` (immutable-ish struct) and ports. Ports are injected by the application layer.

---

## 4) Data flow (happy path)

1) API receives multipart (file, fio, optional reason/doc_type).
2) Application `process_document` saves file via `StoragePort`, builds `RunContext` with dirs.
3) Domain `run_pipeline` executes stages against ports:
   - acquire → ocr → doc‑type → extract (+stamp) → merge → validate → finalize
4) Domain returns `{run_id, verdict, errors, artifacts}`.
5) Application writes manifests/final JSON via `StoragePort` and returns API response models.

---

## 5) Observability & errors

- Middleware measures per‑request durations; application/pipeline records per‑stage duration with `metrics.record_stage_duration`.
- Logs: structured, include `run_id`, `stage`, and redacted PII later.
- Domain exposes error codes; API maps to HTTP using `observability/errors.py` so clients see consistent codes.

---

## 6) Configuration (env)

Add to `core/config.py`:
- `OCR_BASE_URL`, `OCR_TIMEOUT_SECONDS`, `OCR_VERIFY_SSL`
- `LLM_BASE_URL`, `LLM_TIMEOUT_SECONDS`, `LLM_VERIFY_SSL`
- `MAX_PDF_PAGES`, `STAMP_ENABLED`
- Keep `RUNS_DIR`, `TRACING_ENABLED`, etc.

Application constructs adapters with these settings and injects into use‑cases.

---

## 7) Security (later but designed‑in | SKIP FOR NOW | DO NOT IMPLEMENT YET )

- Keep `/docs`, `/health`, `/ready` optionally open; `/v1/*` behind JWT/mTLS (Phase 4 when you enable it).
- Never log raw PII; redact in logging helpers.
- Retention cleanup for `runs/` (cron or background task) before prod.

---

## 8) Phased migration plan (from main‑dev)

Each phase ends with tests and acceptance criteria. Avoid long‑running branches.

- **Phase 0 – Prepare scaffolding (no behavior change)**
  - Create `application/`, `domain/`, `infrastructure/`, `core/`, update `main.py` if needed.
  - Introduce ports (interfaces) and placeholders.
  - Acceptance: service still boots; existing `/v1/*` endpoints untouched.

- **Phase 1 – Define domain contracts and models**
  - `domain/pipeline/constants.py`, `models.py`, `errors.py`, `ports/`.
  - Acceptance: unit tests compile and pass for contracts; no runtime changes.

- **Phase 2 – Implement infrastructure adapters**
  - `infrastructure/storage/local_disk.py` implements `StoragePort` using existing storage layout.
  - `infrastructure/clients/ocr_http.py` and `llm_http.py` implement ports with httpx.
  - Acceptance: adapter unit tests against dev endpoints (mockable).

- **Phase 3 – Rebuild pipeline stages (pure domain)**
  - Port logic from main‑dev into `domain/pipeline/stages` and `orchestrator.py`.
  - No file/HTTP in domain; use ports for all side effects.
  - Acceptance: domain integration tests run pipeline with fake ports and sample JSON.

- **Phase 4 – Wire application use‑cases**
  - `application/usecases/process_document.py` composes adapters + domain `run_pipeline`.
  - `application/services/pipeline_runner.py` times and calls use‑case.
  - Acceptance: `/v1/process` returns realistic verdict/errors on sample files.

- **Phase 5 – Async jobs**
  - Ensure jobs background task calls the new use‑case; persist job status and artifacts.
  - Acceptance: `/v1/jobs` → `/v1/jobs/{id}` flows to completion with artifacts.

- **Phase 6 – Observability pass**
  - Per‑stage metrics wired; error codes audited; log context enriched.
  - Acceptance: `/metrics` shows stage histograms; logs have `run_id` and stage info.

- **Phase 7 – Parity & hardening**
  - Compare outputs against main‑dev for a curated set of docs.
  - Fix edge cases (page limits, doc‑type unknowns, extractor schema mismatches).
  - Acceptance: parity report within agreed tolerance.

- **Phase 8 – Optional integrations**
  - Add `infrastructure/storage/s3_minio.py` and/or Kafka consumer.
  - Acceptance: feature-flagged; tests cover adapters.

---

## 9) Testing strategy

- **Unit**: domain stages with fake ports; adapters with httpx mocks; schema validation.
- **Integration**: `/v1/process` and `/v1/jobs` with sample files; verify `runs/` artifacts.
- **Performance smoke**: 5–10 concurrent requests; observe P95 latency and failures.
- **Parity**: compare selected outputs against main‑dev artifacts.

---

## 10) Deployment & operations

- Continue with Docker multi‑stage build; run with Gunicorn+Uvicorn workers.
- For air‑gapped servers, build `linux/amd64` on CI/Mac with `buildx --platform` or build on server.
- Run behind company gateway/NGINX; later add Phase 4 auth at app or edge.

---

## 11) Coding standards & conventions

- Python 3.12; Pydantic v2 models; type hints everywhere.
- No business logic in FastAPI route functions; all in application/domain.
- Ports return well‑typed results; domain raises domain errors only.
- Avoid global state; inject dependencies via constructors or FastAPI lifespan.
- Small modules; descriptive names; no circular imports.

---

## 12) Work breakdown (who does what)

- **Backend**: domain ports/stages/orchestrator, adapters, use‑cases, routes.
- **AI/ML**: tune LLM prompts/processors; provide sample docs and expected outputs.
- **DevOps**: CI buildx, internal registry, NGINX/gateway config, logging/metrics sinks.
- **QA**: parity harness, regression samples, performance checklist.

---

## 13) Acceptance checklist (service‑level)

- Domain pipeline runs with only ports injected; unit+integration tests pass.
- API returns stable schema; error codes standardized.
- Metrics show per‑endpoint and per‑stage timings; logs are structured with request/run IDs.
- Container runs on Debian 12 server; `/health`, `/ready`, `/metrics`, `/docs` work.
- No imports from `apps/main-dev` remain.

---

## 14) Appendix – minimal code skeletons (conceptual)

Storage port:
```python
class StoragePort(Protocol):
    def save_input(self, run_id: str, src_path: str) -> Path: ...
    def write_json(self, run_id: str, rel_path: str, obj: dict) -> Path: ...
    def read_json(self, run_id: str, rel_path: str) -> dict: ...
    def ensure_dirs(self, run_id: str, *rel_dirs: str) -> None: ...
```

FastAPI route → use‑case wiring:
```python
@router.post("/process")
async def process(file: UploadFile = File(...), fio: str = Form(...)):
    adapters = build_adapters_from_settings(get_settings())
    result = await process_document(file, fio, adapters)
    return ProcessResponse(**result)
```

This design yields a cleaner, testable, future‑proof service that recreates main‑dev’s behavior without inheriting its coupling.
