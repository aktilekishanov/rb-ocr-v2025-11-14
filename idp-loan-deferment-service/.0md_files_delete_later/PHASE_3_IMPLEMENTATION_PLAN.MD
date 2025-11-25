# Phase 3 – Observability & Resilience: Implementation Plan

Scope: add baseline observability (metrics, tracing hooks, error mapping) and resilience (timeouts, retries) on top of Phase 1–2.
This phase does not add new business logic. It improves how we see, instrument, and recover from failures.

---

## 1. Goals

In plain words: Phase 3 is about **seeing what the service is doing** and **failing more gracefully**. We are not changing business rules, only how we monitor and protect them.

- Expose minimal internal metrics to gauge health and performance.
- Standardize error codes and mapping at the API boundary.
- Add timeouts/retries around expensive/IO operations (future‑proof for OCR/LLM and S3).
- Keep logs structured and correlated; optionally enrich with trace IDs.

---

## 2. Directory and files to create/extend

Under `apps/idp-loan-deferment-service/`:

- **App package additions**
  - `app/observability/__init__.py`
  - `app/observability/metrics.py` – counters, timers, and export endpoints.
  - `app/observability/tracing.py` – optional OpenTelemetry wiring (no vendor lock‑in).
  - `app/observability/errors.py` – error code registry and mappers.

- **Extensions to existing modules**
  - `app/main.py` – include metrics endpoint(s) and tracing init.
  - `app/api/v1/routes_process.py` – add metrics and error mapping wrappers.
  - `app/api/v1/routes_jobs.py` – add metrics and error mapping wrappers.
  - `app/services/pipeline_runner.py` – measure per‑stage timings (placeholders now).
  - `app/services/jobs.py` – count job submissions, completions, failures.

---

## 3. Metrics – `app/observability/metrics.py`

**For non‑tech readers:** Metrics are **numeric counters and timers** that tell us how many requests we handled, how long they took, and how many jobs succeeded or failed. They are meant for dashboards and alerts, not for business users.

Glossary of tools mentioned here:
- **`prometheus_client`** – a small Python library that lets us expose internal numbers over HTTP.
- **Prometheus** – an open‑source monitoring system that regularly calls `/metrics` and stores those numbers.
- **Grafana** – a dashboard tool that can graph Prometheus data over time.
- **Histogram** – a metric type that groups timings into buckets (e.g., "how many requests finished under 0.1s, 0.5s, 1s...").
- **Decorator** – a small wrapper around a function in code that can add behavior (e.g., start/stop a timer) without changing the function body.

### 3.1 What to export
- **Counters**
  - `requests_total{endpoint,method,status}`
  - `jobs_submitted_total`
  - `jobs_completed_total`
  - `jobs_failed_total`
- **Timers (histograms)**
  - `request_duration_seconds{endpoint,method}`
  - `pipeline_duration_seconds`

### 3.2 Implementation approach

In practice we will:

- Use `prometheus_client` (a standard metrics library) to collect numbers in memory.
- Provide a `/metrics` HTTP endpoint that monitoring systems (Prometheus, Grafana) can scrape.
- Add small helper decorators for developers:
  - `@track_request(endpoint_name)` to time endpoints and increment request counters.
  - `record_pipeline_duration(seconds)` to record how long a pipeline run took.

### 3.3 Steps
1. Add `prometheus_client` to requirements (dev friendly, no breaking change).
2. Implement global registry and collectors.
3. Add `router.get("/metrics")` or expose via `app.add_route("/metrics", metrics_asgi_app)`.
4. Wrap Phase 1 (`/v1/process`) and Phase 2 (`/v1/jobs`, `GET /v1/jobs/{run_id}`) with timing decorators.

---

## 4. Tracing hooks – `app/observability/tracing.py` (optional)

**For non‑tech readers:** Tracing is like assigning a **tracking number** to each request and following it through all internal calls (OCR, LLM, S3, etc.). It helps answer "where did we spend time?" when something is slow.

Glossary:
- **OpenTelemetry (OTel)** – an open standard and set of libraries for collecting traces, metrics, and logs in a vendor‑neutral way.
- **Tracer provider** – the object that creates and manages trace spans (logical units of work) for each request.

### 4.1 What to add
- Initialize OpenTelemetry SDK only if env vars are present (feature flag by configuration).
- Create a tracer provider and instrument FastAPI routes (middleware).

### 4.2 Why
- Later, when calling OCR/LLM and S3, traces help correlate latencies and failures.
- Keep this optional in Phase 3 to avoid complexity.

### 4.3 Steps
1. Add optional dependencies (e.g., `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`) guarded by try/except.
2. Provide `init_tracing_if_enabled(settings)` function.
3. Call it in `app/main.py` during startup.

---

## 5. Error mapping – `app/observability/errors.py`

**For non‑tech readers:** Error mapping is about giving **consistent, easy‑to‑search error codes** to external systems, instead of ad‑hoc text messages. This makes integration and support much easier.

Glossary:
- **HTTPException (FastAPI)** – the standard way to return an HTTP error (with status code and JSON body) from a FastAPI endpoint.
- **Error code** – a short machine‑readable string (e.g., `JOB_NOT_FOUND`) that appears both in logs and API responses.

### 5.1 Error registry
- Define stable API error codes with human‑readable messages:
  - `UNSUPPORTED_FILE_TYPE`
  - `UPLOAD_READ_FAILED`
  - `INTERNAL_PROCESSING_ERROR`
  - `JOB_SUBMIT_FAILED`
  - `JOB_NOT_FOUND`
- Provide helper `to_http_error(code, message=None, status=400)` to build consistent `HTTPException` payloads.

### 5.2 Apply to routes
- Replace ad‑hoc `HTTPException(detail=...)` with `to_http_error(...)` for consistency.
- Keep response models unchanged (only detail struct standardizes).

---

## 6. Timeouts and retries (foundations)

**For non‑tech readers:** Timeouts and retries are safety rails for network calls. Instead of hanging forever or failing once, we:
- Wait only a reasonable amount of time (timeout).
- Optionally try again a few times with short pauses (retries).

### 6.1 Where to apply now
- File I/O and storage operations are local and fast; we’ll prepare hooks for future external calls.
- Add a simple retry util in `app/observability/retries.py`:
  - `async_retry(fn, retries=2, backoff=0.2, max_backoff=1.0)`
  - `retry(fn, ...)` sync variant

### 6.2 Future hooks
- When introducing OCR/LLM and S3/MinIO in later phases, wrap network calls using these retry utilities and add timeouts (`asyncio.wait_for` or client‑level timeouts).

---

## 7. Wiring in `app/main.py`

- Import metrics/tracing initializers.
- On startup:
  - `init_tracing_if_enabled(settings)` (no‑op if not configured).
- Expose `/metrics` endpoint.
- Add middleware (if tracing enabled) before routers.

---

## 8. Tests & manual verification

### 8.1 Manual checks
- Start the service and open `/metrics` → verify counters/histograms exist and update after requests.
- Submit jobs and see `jobs_submitted_total`, `jobs_completed_total` change.

### 8.2 Automated tests (optional)
- Add `tests/test_metrics.py`:
  - Hit `/health`, `/ready`, `/v1/process`.
  - Assert metrics endpoint contains expected counters and increments.

---

## 9. Acceptance criteria for Phase 3
- `/metrics` endpoint exists and returns Prometheus exposition format.
- Request/endpoint counters and durations are recorded for Phase 1–2 endpoints.
- Job counters exist for submit/completion/failure.
- Error mapping utility is used in jobs and process routes for consistent responses.
- Tracing hooks exist and are initialized only when enabled via env.

---

## 10. Notes & future upgrades
- Prometheus client works for dev/stage quickly; later we can switch to an enterprise stack if needed.
- Tracing wiring is optional; turn on in environments where collectors exist.
- Retries/timeouts utilities are placeholders for future external calls (OCR/LLM/S3, Kafka callbacks).
