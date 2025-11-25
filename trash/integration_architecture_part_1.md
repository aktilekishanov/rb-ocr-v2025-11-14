# Integration Architecture – Part 1: Microservice Foundation

This document describes how to implement the **microservice foundation** for the Loan Deferment IDP service. Scope of this part:

- **Headless service**: no UI, long-running worker.
- **FastAPI-based HTTP layer** for health/readiness and (optionally) admin/debug endpoints.
- **Process model** for running the Kafka consumer and pipeline worker.
- **Configuration, logging, and observability** basics.
- **Packaging & run modes** for local/dev and deployment.

It intentionally does **not** cover full Kafka/MinIO/callback logic – only the skeleton required for them.

---

## 1. High-level design

- **Service type**: Long-running Python process with two responsibilities:
  - **HTTP control plane** (FastAPI): health, readiness, basic info.
  - **Background worker plane**: Kafka consumer loop that triggers the IDP pipeline.
- **Run mode**:
  - Single container/process in dev.
  - In prod, we can either:
    - Run **one process** that starts both FastAPI and the consumer (simpler).
    - Or split into **two deployments**: `idp-api` (FastAPI only) and `idp-worker` (consumer only). Start with single-process; keep code structured to allow later split.
- **State**: stateless per request; all durable state goes to external stores (Kafka offsets, S3/MinIO, DB if added, logs).

---

## 2. Project structure (microservice layer)

Suggested additions on top of existing RB-OCR/IDP code:

```text
main-dev/
  rb-ocr/
    rbidp/
      ... existing orchestrator/pipeline ...
    service/
      __init__.py
      config.py          # Typed settings via pydantic-settings
      logging.py         # Logging setup (JSON/structured-ready)
      app.py             # FastAPI app, routers, lifecycles
      health.py          # Health/readiness logic
      consumer.py        # Kafka consumer lifecycle hooks
      runner.py          # Entry points for different run modes
```

If you prefer to keep it under `main/` instead of `main-dev/`, mirror the same `service/` package there.

---

## 3. Configuration model

Use **environment-driven config** (12-factor style) with a typed config class.

### 3.1. Config fields (initial)

In `service/config.py` define a `Settings` class (e.g. using `pydantic_settings.BaseSettings`):

- **Service basics**
  - `service_name: str = "loan-deferment-idp"`
  - `environment: str` – `dev|stage|prod`.
  - `log_level: str` – `INFO|DEBUG|WARN|ERROR`.

- **HTTP server**
  - `http_host: str = "0.0.0.0"`
  - `http_port: int = 8080`

- **Kafka (skeleton only in Part 1)**
  - `kafka_bootstrap_servers: str`
  - `kafka_docs_topic: str = "di-loan-delay.event.docs-uploaded"`
  - `kafka_consumer_group: str = "loan-deferment-idp"`

- **S3/MinIO (placeholder)**
  - `s3_endpoint_url: str = "https://s3-dev.fortebank.com:9443"`
  - `s3_access_key: str`
  - `s3_secret_key: str`
  - `s3_bucket_default: str = "loan-statements-dev"`

- **Pipeline**
  - Timeouts, concurrency limits, feature flags (can be filled in Part 2+).

Expose a global `get_settings()` function that returns a singleton `Settings` instance (cached) to avoid reparsing env every time.

---

## 4. Logging & observability skeleton

In `service/logging.py`:

- Configure standard `logging` with:
  - Level from settings.
  - Format that includes at least: `timestamp`, `level`, `logger`, `message`, `request_id`, `run_id` if present.
- Prepare helper for contextual logging:
  - A function `get_logger(name: str)` that returns a logger with basic config applied.
- In later parts, we can add:
  - JSON formatter
  - Correlation ID middleware for HTTP requests
  - Integration with any central log collector.

This file should be imported and executed early (e.g., from `service/app.py` and `service/runner.py`).

---

## 5. FastAPI app – health & readiness

In `service/app.py`:

1. **Create FastAPI application**
   - Instantiate `FastAPI(title="Loan Deferment IDP", version="0.1.0")`.

2. **Include health endpoints** (see also `health.py`):
   - `GET /health` – **liveness**: process is up, event loop active.
     - Simple implementation: always returns `{status: "ok"}` as long as the app responds.
   - `GET /ready` – **readiness**: service is ready to handle Kafka and external calls.
     - Implementation should check at least:
       - Kafka connectivity status flag (set by `consumer.py`).
       - Optionally S3/MinIO readiness flag.
     - Return `{status: "ready"}` when all checks pass; otherwise `{status: "not_ready", details: {...}}` with `503` status.

3. **Optional basic info endpoint**
   - `GET /info` – service metadata; returns version, environment, git commit hash (if injected via env), etc.

4. **Lifecycle events**
   - `@app.on_event("startup")`:
     - Initialize logging.
     - Initialize global `Settings`.
     - Optionally start background tasks (if we choose to run consumer from here).
   - `@app.on_event("shutdown")`:
     - Gracefully stop background worker/consumer (if running in same process).

`health.py` should contain reusable functions that the endpoints call, e.g. `check_readiness()` that returns a structured object.

---

## 6. Background worker / Kafka consumer process model

We want flexibility to run:

- **Mode A (combined)**: One process/container with both FastAPI and Kafka consumer.
- **Mode B (split)**: Separate `api` and `worker` deployments.

### 6.1. Entry-points

In `service/runner.py` define functions and console entry points:

- `run_api()` – starts FastAPI with `uvicorn`.
- `run_worker()` – starts Kafka consumer loop (no HTTP server).
- `run_all()` – starts both in-process (for dev or simple deployments).

Implementation sketch:

- `run_api()`: call `uvicorn.run("rb_ocr.service.app:app", host=settings.http_host, port=settings.http_port, ...)`.
- `run_worker()`: import `consumer.run_consumer_loop()` and call it.
- `run_all()`: use `asyncio` or threading to start both; or in dev simply start `uvicorn` and have it start the consumer in a startup event.

We will refine the exact pattern once Kafka integration details are fixed; Part 1 only requires stubs and basic wiring.

### 6.2. Consumer lifecycle skeleton

In `service/consumer.py`:

- Define an enum/state holder:
  - `ConsumerState` with fields like: `is_running: bool`, `last_error: Optional[str]`, `last_healthy_ts: datetime`.
- Provide functions:
  - `start_consumer_background()` – to be called from FastAPI startup if using Mode A.
  - `stop_consumer()` – to be called on shutdown.
  - `get_consumer_health()` – used by readiness check.

For Part 1, the actual Kafka consumption loop can be:

- Either **stubbed** (e.g., loop with sleep and logging) to validate lifecycle.
- Or minimally implemented but with no real business logic.

---

## 7. Health/readiness logic details

In `health.py`:

- **Liveness**: trivial; if the HTTP server responds, liveness = ok.
- **Readiness**:
  - Aggregate health from:
    - `consumer.get_consumer_health()` – is consumer running and not in fatal error.
    - (Later) `s3_client.is_healthy()` – optional.
  - Define a small `ReadinessStatus` model:
    - `status: Literal["ready", "not_ready"]`
    - `components: dict[str, str]` – status per component: `"consumer": "ok|starting|error"`, etc.

Example behavior:

- On startup before consumer connects, `/ready` returns `503` with `status="not_ready"` and `components={"consumer": "starting"}`.
- After successful consumer initialization, `/ready` returns `200` with `status="ready"`.

---

## 8. Integration with existing IDP pipeline

While Part 1 does not implement the full Kafka → pipeline path, code should be **structured** to plug into the existing orchestrator:

- Introduce an adapter module later, e.g. `service/pipeline_adapter.py` that wraps the existing `run_pipeline(...)` function from `rbidp`.
- Ensure `consumer.py` is designed to, for each Kafka message:
  - Parse event → construct `PipelineContext`/input DTO.
  - Call the orchestrator.
  - Handle results and errors.

This is for future parts; Part 1 only needs to define where this will be plugged in.

---

## 9. Deployment & run commands (baseline)

### 9.1. Local/dev

- Install dependencies (example):
  - `fastapi`
  - `uvicorn[standard]`
  - `pydantic-settings` (if used)

- Start API only:
  - `python -m rb_ocr.service.runner api`

- Start worker only:
  - `python -m rb_ocr.service.runner worker`

- Start both (dev-only):
  - `python -m rb_ocr.service.runner all`

(Exact CLI shape is up to you; we can add `argparse`/`typer` in `runner.py`.)

### 9.2. Containerization (outline)

In a later step, create a `Dockerfile` with two possible `CMD`s:

- `CMD ["python", "-m", "rb_ocr.service.runner", "api"]` – API-only pod.
- `CMD ["python", "-m", "rb_ocr.service.runner", "worker"]` – worker-only pod.

For now, Part 1 only needs the Python entry points and a clear process model.

---

## 10. Step-by-step implementation plan (Part 1)

1. **Create `service` package** under the chosen project root (e.g. `main-dev/rb-ocr/rbidp/service`).
2. **Add `config.py`**
   - Implement `Settings` with fields listed above.
   - Implement `get_settings()` singleton.
3. **Add `logging.py`**
   - Configure root logger from settings.
   - Provide `get_logger(name)` helper.
4. **Add `health.py`**
   - Define models for readiness response.
   - Implement `check_liveness()` and `check_readiness()`.
5. **Add `consumer.py` (skeleton)**
   - Define `ConsumerState` and in-memory state variable.
   - Implement `start_consumer_background()` and `get_consumer_health()` with stub loop.
6. **Add `app.py`**
   - Create FastAPI `app`.
   - Wire `/health`, `/ready`, `/info` endpoints using `health.py` utilities.
   - Use startup/shutdown events to initialize logging, settings, and (optionally) start consumer background task.
7. **Add `runner.py`**
   - Implement CLI (e.g., `python -m rb_ocr.service.runner [api|worker|all]`).
   - Map modes to `run_api()`, `run_worker()`, `run_all()`.
8. **Wire imports from existing code**
   - Ensure `rbidp` package is importable from the new service package (update `__init__.py` if needed).
9. **Smoke test**
   - Run API locally; verify `/health` and `/ready` endpoints.
   - If consumer stub is enabled, see logs confirming it runs.
10. **Document run instructions**
   - Add a short section in `README` or in this doc for how to start API and worker in dev.

This completes **Part 1: Microservice foundation** and prepares the codebase for adding concrete Kafka, MinIO, and callback integrations in subsequent parts.
