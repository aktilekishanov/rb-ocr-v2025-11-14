# RB Loan Deferment IDP — Scalability Review and FastAPI Service Plan

This report complements REPORT.MD with a focus on scalability and the migration path to a production-ready FastAPI service.

## 1) Scalability of the As‑Is (Streamlit + Orchestrator)

- **Strengths**
  - **Modular pipeline**: Orchestrator is cleanly staged (acquire → OCR → LLM checks → merge → validate) and already decoupled from the UI entrypoint.
  - **Typed contracts**: DTOs and curated artifacts simplify moving to service boundaries and versioning.
  - **Deterministic artifacts**: Per-run folder layout makes troubleshooting predictable.

- **Bottlenecks / Limits**
  - **Runtime container (Streamlit) is not an API server**
    - Not designed for sustained concurrency, backpressure, or API lifecycle (health/readiness, graceful shutdown, middlewares, auth).
    - In-process runs block worker threads; no queue; limited throughput under load.
  - **Blocking orchestration around async OCR**
    - `ask_tesseract` uses an async client but bridges to sync with new event loops when needed; under concurrency this pattern is inefficient and error-prone. --------------------(IMPORTANT!) --------------------
  - **Local filesystem for artifacts**
    - Artifacts are written to local disk. Horizontal scaling with multiple replicas requires shared storage (S3/MinIO, NFS) or a storage abstraction.
  - **No idempotency or job control**
    - Lacks job submission/status APIs, deduplication by `request_id`, retry/backoff strategies, and DLQ. Hard to operate at-least-once semantics reliably.
  - **Lack of operational hooks**
    - No out-of-the-box structured logging correlation, metrics, tracing, rate limits, or circuit breakers.
  - **Security and configurability gaps (dev-only)**
    - LLM client disables TLS verification; stamp detector uses hardcoded paths; timeouts are static.

- **Practical impact**
  - Works well as an MVP and for manual runs.
  - Not suitable as-is for production traffic spikes, parallel processing, or HA deployments without significant scaffolding around it.

## 2) Why make it a FastAPI service (Pros)

- **Production-grade API surface**
  - ASGI-based concurrency (uvicorn/gunicorn with multiple workers), request lifecycle, middlewares, and standard HTTP semantics.
  - Built-in OpenAPI/Swagger for contracts; first-class Pydantic models and validation.
- **Async-first I/O performance**
  - Natural fit for the async Dev OCR client; allows concurrent in-flight OCR/LLM requests with fewer threads.
  - Easy to upgrade LLM client to `httpx.AsyncClient` for end-to-end async.
- **Observability and reliability**
  - Middlewares for structured logging, correlation IDs, metrics (Prometheus), Sentry/OTel tracing, rate limits, timeouts, and retries.
- **Job control and integration patterns**
  - Expose synchronous “process now” and asynchronous “submit job → poll/callback” APIs.
  - Integrate background workers (Celery/RQ/Dramatiq) or lightweight in-process queues for backpressure.
- **Horizontal scaling**
  - Stateless API instances fronted by a load balancer; artifacts stored in MinIO/S3; run metadata persisted in DB/Redis.
- **Security and governance**
  - MTLS/TLS termination, authN/Z, request signing, secrets via env/VAULT, audit trails.
- **Smooth path to event-driven**
  - Coexists with Kafka-based ingestion: same orchestrator and storage abstractions, separate process/worker for the consumer.

## 3) What needs to be done to make it a FastAPI service

- **3.1 API design (v1)**
  - **Health**: `GET /health`, `GET /ready`.
  - **Synchronous processing (small docs, demo, backoffice)**:
    - `POST /v1/process` (multipart or JSON with `s3_path`), body: `{ fio, reason, doc_type, file | s3_path }`.
    - Returns 200 with `{ run_id, verdict, errors, timings, artifact_paths? }` or 202 with `{ run_id }` if forced async.
  - **Asynchronous jobs (recommended for scale)**:
    - `POST /v1/jobs` → returns `{ run_id }` immediately.
    - `GET /v1/jobs/{run_id}` → returns `{ status, verdict?, errors?, progress?, links }`.
    - Optional: `POST /v1/jobs/{run_id}/cancel`.
    - Optional callback/webhook registration per job.
  - **Artifacts**:
    - `GET /v1/jobs/{run_id}/artifacts/{name}` to fetch curated JSONs, gated by auth.

- **3.2 Service skeleton**
  - Framework: FastAPI + uvicorn (optionally gunicorn workers).
  - Project layout: `app/` (routers, models, services), `pipeline/` (existing orchestrator), `config/`, `deps/`.
  - Env-driven config (12-factor): OCR/LLM base URLs, timeouts, RB_IDP_RUNS_DIR, RB_IDP_STAMP_ENABLED, MinIO creds, DB/Redis URLs.

- **3.3 Orchestrator integration**
  - Keep `run_pipeline(...)` as the core; make it callable from:
    - Sync endpoint (blocking path) for small loads.
    - Background task/worker for async jobs; persist job state.
  - Replace `llm_client` with `httpx.AsyncClient` (verify TLS) and provide retry/backoff.
  - Remove new-event-loop bridging in `ask_tesseract`; use native `await` in FastAPI handlers or worker.

- **3.4 Storage and state**
  - **Artifacts**: Abstract a storage layer with S3/MinIO backend (recommended). Keep the current folder semantics as object keys (`runs/<date>/<run_id>/...`).
  - **Metadata**: Store job rows in Postgres (or Redis streams) for idempotency and status transitions (submitted → running → completed/failed).
  - **Idempotency**: Upsert on `request_id` (if provided) to dedupe.

- **3.5 Background processing**
  - Choose one:
    - Celery + Redis/RabbitMQ (mature, resilient queues, scheduling, retries, visibility).
    - Dramatiq/RQ for lighter setups.
    - Or start with FastAPI BackgroundTasks, then graduate to a proper queue.
  - Encode retry policies (OCR/LLM timeouts), DLQ for poison payloads.

- **3.6 Observability and ops**
  - Structured logs (JSON), correlation IDs (`request_id`, `run_id`).
  - Metrics: per-stage latencies, success/failure counters, queue depth, OCR/LLM error rates.
  - Tracing: OpenTelemetry spans across OCR/LLM calls.
  - Alerts: SLOs for latency and error ratio.

- **3.7 Security**
  - Enforce TLS and certificate verification.
  - mTLS or OAuth/JWT for clients; RBAC for artifact access.
  - Secrets from environment/VAULT; zero hardcoded paths for stamp.

- **3.8 Packaging & deployment**
  - Dockerfile, CI/CD, Helm/K8s manifests (HPA on CPU/RPS), readiness/liveness probes.
  - Resource limits/requests; per-env config; blue/green or rolling deploys.

- **3.9 Compatibility with event-driven integration**
  - Kafka consumer as a separate worker using the same orchestrator module.
  - MinIO/S3 fetch for input (`s3_path`) and artifact writeback; REST callback publisher after completion.

### Can we start from scratch and do it?

- **Short answer**: Yes—start “from scratch” for the service scaffolding, but **reuse the existing orchestrator and processors** to minimize risk and delivery time.
- **Recommended approach**
  - New `service/` package (FastAPI skeleton) + dependency-injected pipeline runner.
  - Keep current `pipeline/` intact; refactor clients (LLM/OCR) to async and configurable.
  - Introduce storage abstraction (local FS vs MinIO) behind a clean interface.
- **Why not rewrite the pipeline?**
  - It is already modular, typed, and battle-tested in MVP. Rewriting increases risk and delays; the gains do not justify the cost.

## 4) Minimal target architecture (v1)

- **API**: FastAPI, `/v1/jobs` (async), `/v1/process` (sync), `/health`, `/ready`.
- **Workers**: Celery (Redis) running `run_pipeline` with async I/O (OCR/LLM).
- **Storage**: MinIO for artifacts, Postgres for jobs (id, status, started_at, finished_at, verdict, errors).
- **Security**: TLS/mTLS, secrets via env; verified certificates.
- **Deploy**: Docker + K8s with 2–3 replicas, HPA on CPU/RPS, shared MinIO.

## 5) Step-by-step migration plan

- **Phase 0 — Prep**
  - Abstract storage; parameterize paths; move stamp detector config to env.
  - Make LLM client async with verified TLS and retries.
- **Phase 1 — FastAPI skeleton**
  - Implement `/health`, `/ready`, `/v1/process` (blocking) using current orchestrator.
  - Add structured logging and correlation IDs.
- **Phase 2 — Background jobs**
  - Add Celery + Redis, `/v1/jobs` submit/poll endpoints, job table (Postgres).
  - Idempotency on `request_id`; exponential backoff for OCR/LLM.
- **Phase 3 — Storage to MinIO**
  - Switch artifact writes to MinIO; keep local as a dev fallback.
  - Provide signed URLs for artifact retrieval.
- **Phase 4 — Observability & hardening**
  - Metrics, tracing, rate limits, circuit breakers, resource limits.
  - Security hardening (TLS, auth), load/perf tests; readiness for bank traffic.
- **Phase 5 — Kafka integration (optional)**
  - Separate consumer worker that enqueues jobs; REST callback publisher.

## 6) Risks and mitigations

- **External dependencies**: OCR/LLM latencies and errors dominate tail. Mitigate with retries, jittered backoff, circuit-breakers, and concurrency caps.
- **Artifact storage growth**: S3 lifecycle policies and retention windows; optional compression.
- **Stamp detector CPU**: Offload heavy rendering/detection to a separate worker pool; cache results per file hash.
- **TLS and certificates**: Validate cert chains; pin certs in non-internet environments.

## 7) Initial backlog (actionable)

- **(A)** FastAPI app skeleton with `/health`, `/ready`, `/v1/process`.
- **(B)** Async LLM client; remove loop-bridging in OCR client path.
- **(C)** Storage abstraction + MinIO backend.
- **(D)** Job model (Postgres) + Celery integration + `/v1/jobs` APIs.
- **(E)** Structured logging, metrics, tracing; security configuration.
- **(F)** Dockerfile + K8s manifests; per-env config; CI pipeline.

---

### TL;DR
- The current solution is an excellent MVP for manual testing but not scalable as a service.
- FastAPI brings async concurrency, operability, observability, and security that we need for production.
- Start from scratch for the service skeleton, but reuse and evolve the existing orchestrator and processors to deliver quickly with lower risk.
