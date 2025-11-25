# Phase 3 – Observability & Resilience: Explanation

This document explains every part added in Phase 3, what it is, why it’s needed, and how it works, using simple language and concrete references to the code.

## Plain‑language summary
Phase 3 adds basic visibility into the service and makes the API’s errors predictable:
- We expose live service metrics at `/metrics` in Prometheus format.
- We record request counts and timing, and the overall pipeline processing time.
- We standardize error responses with stable error codes.
- We left optional tracing and retry utilities as future extensions.

# Components

## Metrics primitives (counters and histograms)
- **What**
  - Prometheus metrics are defined in `app/observability/metrics.py`.
  - Counters (always increase) and histograms (bucketed timings):
    - `http_requests_total{endpoint,method,status}`
    - `http_request_duration_seconds{endpoint,method}`
    - `pipeline_duration_seconds`
    - `jobs_submitted_total`, `jobs_completed_total`, `jobs_failed_total`
- **Why**
  - To understand traffic and latency, spot errors quickly, and build dashboards/alerts in Grafana.
- **How**
  - We use `prometheus_client` to define metrics. If the dependency is missing, safe fallbacks return an empty `/metrics` response so the app never crashes.

## MetricsMiddleware
- **What**
  - `MetricsMiddleware` in `metrics.py` measures every HTTP request.
- **Why**
  - Consistent, automatic measurement of request counts and timings across all endpoints.
- **How**
  - On each request, it:
    - Records start time.
    - Calls the downstream handler.
    - Increments `http_requests_total` with labels: `endpoint` (route template like `/v1/jobs/{run_id}`), `method`, `status`.
    - Observes duration in `http_request_duration_seconds` with labels `endpoint`, `method`.
  - On exceptions, it still increments counters and records duration, then re-raises.

## /metrics endpoint
- **What**
  - A FastAPI router mounted at `/metrics` serves Prometheus text format.
- **Why**
  - To let Prometheus scrape the app and feed dashboards/alerts.
- **How**
  - `metrics_router` in `metrics.py` exposes `generate_latest()` output.
  - In `app/main.py`, we `include_router(metrics_router)`.
  - If `prometheus_client` is not installed, the endpoint returns an empty body (still 200). Install the dependency to get full output.

## Pipeline duration recording
- **What**
  - We measure end‑to‑end processing time of the Phase 1 pipeline.
- **Why**
  - To know how long processing takes in practice and watch for regressions.
- **How**
  - `run_sync_pipeline` in `app/services/pipeline_runner.py` uses `time.perf_counter()` and calls `record_pipeline_duration(...)` after completion.
  - Fail‑safe: if metrics are disabled or errors occur, the pipeline still completes.

## Standardized error registry and mapper
- **What**
  - A small error code registry and `to_http_error(...)` helper in `app/observability/errors.py`.
- **Why**
  - Consistent error format makes debugging, logs, dashboards, and client integrations more reliable.
- **How**
  - Routes call `to_http_error("<CODE>")` instead of crafting ad‑hoc errors.
  - Example codes used:
    - `UNSUPPORTED_FILE_TYPE` (400)
    - `UPLOAD_READ_FAILED` (400)
    - `INTERNAL_PROCESSING_ERROR` (500)
    - `JOB_SUBMIT_FAILED` (500)
    - `JOB_NOT_FOUND` (404)
  - Response shape is consistent: `{"detail": {"code": "...", "message": "..."}}`.

## Optional tracing hooks (future‑ready)
- **What**
  - Phase 3 plan leaves room for OpenTelemetry tracing.
- **Why**
  - Distributed tracing helps follow a request across services and spot bottlenecks.
- **How**
  - Not enabled in code yet; can be added via an `observability/tracing.py` initializer guarded by env flags.

## Retry/timeouts (future‑ready)
- **What**
  - The plan calls for utilities to wrap outbound network calls with retries/timeouts.
- **Why**
  - Increase resilience to transient errors when integrating with external systems.
- **How**
  - Not implemented yet; will be added when we introduce real external calls (e.g., OCR/LLM, storage, etc.).

# Wiring in main application
- **What**
  - `app/main.py` wires the middleware and routes.
- **Why**
  - Centralized setup ensures every request is measured and `/metrics` is available.
- **How**
  - `app.add_middleware(MetricsMiddleware)`
  - `app.include_router(metrics_router)`

# How to enable and verify
- **Install dependency**
  - Add to environment and reinstall: `prometheus-client` (already in `requirements.txt`).
- **Run and check metrics**
  - Start: `uvicorn app.main:app --reload`
  - Scrape: `curl -s http://localhost:8000/metrics | head`
  - Exercise endpoints:
    - `GET /health`, `GET /ready`
    - `POST /v1/process` (valid and invalid file types)
  - Watch counters and histograms change (e.g., `http_requests_total`, `http_request_duration_seconds`, `pipeline_duration_seconds`).

# Operational notes
- **Dashboards**
  - Prometheus scrapes `/metrics`; Grafana can visualize latency, error rates, and throughput.
- **Security**
  - Consider restricting `/metrics` via network policy or auth if exposed beyond trusted networks.
- **Labels**
  - `endpoint` uses the route template when available (e.g., `/v1/jobs/{run_id}`) to prevent high‑cardinality label explosion.

# Limitations and next steps
- **Tracing** not yet implemented; add optional OpenTelemetry init guarded by env.
- **Retries/Timeouts** to be added once external integrations are wired.
- **Job counters** are defined; wire increments on submit/completion/failure in the job service when needed.
- **Deprecation warnings** (FastAPI `on_event`, Pydantic `Config`) are non‑blocking but should be modernized in a future pass.
