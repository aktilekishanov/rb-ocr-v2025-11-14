# Phase 5 – Packaging & Deployment: Implementation Plan

Scope: package the FastAPI service into a production-ready container and define deployment options (Docker local, Kubernetes optional, or VM/systemd). No business logic changes. The goal is a reliable, repeatable way to run the service in real environments with health checks, logs, and metrics.

---

## 1. Goals (plain language)

- Produce a small, secure Docker image for this service.
- Start with an industry-standard run command:
  - `gunicorn -k uvicorn.workers.UvicornWorker -w <N> app.main:app`
- Support health checks (`/health`, `/ready`) and metrics (`/metrics`).
- Keep logs structured and on stdout (12‑factor friendly).
- Provide sample steps for:
  - Local Docker run.
  - Optional Kubernetes manifests and settings.
  - Optional VM/systemd setup.

---

## 2. Directory and files to create

Under `apps/idp-loan-deferment-service/` (do not create them yet; this plan explains what we will add):

- `Dockerfile` – multi‑stage build, non‑root runtime, pinned dependencies, small final image.
- `.dockerignore` – exclude files that don’t belong in the image (e.g., `.git`, `runs/`, `tests/`, editor caches).
- (Optional) `Makefile` – developer shortcuts (`make build`, `make run`, etc.).

---

## 3. Assumptions and prerequisites

- Phases 0–3 are implemented and test‑green.
- Phase 4 (security hardening) can be deferred in dev; in production you should protect ingress with TLS and, ideally, auth at a gateway.
- Python 3.12; dependencies specified in `requirements.txt`.
- Health endpoints: `/health`, `/ready`.
- Metrics endpoint: `/metrics` (Prometheus exposition).
- Service entrypoint: `app.main:app`.

---

## 4. Docker packaging (what/why/how)

### 4.1 What is a multi‑stage build?
- A Dockerfile split into stages:
  - Builder stage: installs build tools and Python deps, compiles native wheels if needed.
  - Final stage: a slim runtime image with only what’s needed to run the app.
- Why: smaller images, fewer vulnerabilities, faster deploys.

### 4.2 Dockerfile contents (conceptual)
- Base images: `python:3.12-slim` (builder and final).
- Steps:
  1. Set environment (`PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`).
  2. Install OS build dependencies (builder only), e.g., `build-essential`, `gcc`, then remove after.
  3. Copy `requirements.txt`, run `pip install --no-cache-dir -r requirements.txt`.
  4. Copy application code under `/app`.
  5. Create a non‑root user (e.g., `appuser`) and set permissions for `/app` and `/app/runs`.
  6. Expose port 8000; set default `RUNS_DIR=/app/runs`.
  7. Entrypoint/CMD with gunicorn:
     - `gunicorn -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY:-2} -b 0.0.0.0:8000 app.main:app`.

### 4.3 `.dockerignore`
- Keep images small; exclude development artifacts:
  - `.git`, `.github`, `.venv`, `__pycache__`, `*.pyc`, `.DS_Store`
  - `runs/` (unless you want baked‑in test data; not recommended)
  - `tests/`, local `.env` files

### 4.4 Non‑root user and filesystem layout
- Create a user in the image and `USER appuser` before the CMD.
- Ensure `/app/runs` exists and is writable; or mount a volume at runtime.
- This reduces blast radius and meets container security best practices.

### 4.5 Runtime command and tuning
- Base command in container:
  - `gunicorn -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY:-2} -b 0.0.0.0:8000 app.main:app`
- Tuning variables:
  - `WEB_CONCURRENCY`: worker count. Start with `2` on small nodes. Rule of thumb: `CPU cores * 2` for I/O‑bound; adjust by testing.
  - `WORKER_CLASS`: uvicorn worker is suitable for async.
  - `LOG_LEVEL`: keep at `INFO` by default; `DEBUG` only in dev.

---

## 5. Local Docker: build and run (manual verification)

- Build image:
  - `docker build -t idp-loan-deferment-service:local .`
- Run container mapping port and a local volume for runs:
  - `docker run --rm -p 8000:8000 -e IDP_LOG_LEVEL=INFO -e IDP_ENV=dev -v $(pwd)/runs:/app/runs idp-loan-deferment-service:local`
- Verify endpoints:
  - `curl http://localhost:8000/health` → `{ "status": "ok", ... }`
  - `curl http://localhost:8000/ready` → `{ "status": "ok", ... }`
  - `curl http://localhost:8000/metrics | head` → Prometheus metrics present
- Optional: test `/v1/process` and `/v1/jobs*` endpoints as in Phase 1–2 smoke tests.

---

## 6. Observability in containers

- Logs: write to stdout/stderr (already handled by our structured logging). Let the platform collect/ship logs.
- Metrics: keep `/metrics` exposed on the service port; protect it via network policy or auth in production.
- Health: liveness uses `/health`, readiness uses `/ready`.

---

## 7. VM deployment (optional -- do NOT implement yet)

For environments without Kubernetes:

- Install Python and system dependencies (recommended to use Docker even on VMs, but if native):
  - Create a virtualenv, `pip install -r requirements.txt`.
  - Run with `gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000 app.main:app`.
- Systemd unit (conceptual):
  - `[Unit]` Description=IDP Loan Deferment Service After=network.target
  - `[Service]` User=app Group=app WorkingDirectory=/opt/idp ExecStart=/usr/local/bin/gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000 app.main:app Restart=always Environment=IDP_ENV=prod Environment=IDP_LOG_LEVEL=INFO
  - `[Install]` WantedBy=multi-user.target
- Configure reverse proxy (NGINX) for TLS termination and set up health checks.

----

## 8. Acceptance criteria (Phase 5)

- A Docker image builds cleanly and runs the service reliably.
- The container serves `/health`, `/ready`, and `/metrics` as expected.
- Logs appear on stdout in structured form; no crashes on normal traffic.
- Optional: sample k8s manifests validate (pods Ready, probes pass, metrics scrapeable).
- Optional: VM/systemd instructions verified on a test VM.

----

## 9. Risks and mitigations

- Image bloat → use multi‑stage builds, slim base image, `.dockerignore`.
- Wrong worker count → start small, measure latency/CPU, adjust `WEB_CONCURRENCY`.
- Disk usage in `runs/` → mount a volume and (eventually) implement retention cleanup (Phase 4 or ops cron).
- Exposed `/metrics` externally → protect via network/Gateway or toggle auth when Phase 4 is implemented.
- TLS/auth not enforced → deploy behind a gateway that handles TLS and auth until Phase 4 is implemented in the app.

----

## 10. Step‑by‑step checklist (developer‑friendly)

1. Add `.dockerignore` with appropriate exclusions.
2. Create `Dockerfile` with multi‑stage build and non‑root user.
3. Build: `docker build -t idp-loan-deferment-service:local .`
4. Run: `docker run --rm -p 8000:8000 -v $(pwd)/runs:/app/runs idp-loan-deferment-service:local`
5. Verify endpoints: `/health`, `/ready`, `/metrics`, then a sample `/v1/process`.
6. Document environment variables and runtime options for ops.

----

## 11. Environment variables (reference)

- Core:
  - `IDP_APP_NAME` (default `idp-loan-deferment-service`)
  - `IDP_ENV` (e.g., `dev`, `stage`, `prod`)
  - `IDP_LOG_LEVEL` (e.g., `INFO`)
  - `IDP_RUNS_DIR` (default `/app/runs` inside container)
- Observability:
  - `IDP_TRACING_ENABLED` (default `false`, optional, Phase 3)
- Runtime:
  - `WEB_CONCURRENCY` (gunicorn worker count)

----

## 12. Notes

- Security Phase (Phase 4) is planned but intentionally deferred; ensure the deployment environment (gateway/ingress) provides TLS and access control until app‑level auth is added.
- MinIO/S3 migration and Kafka ingestion are planned in Phase 6; the Docker image layout already keeps storage logic isolated so the same container will work when storage is swapped.
