# Phase 0 – Foundations: Implementation Plan

Scope: implement the **minimal skeleton** of the standalone FastAPI service in `apps/idp-loan-deferment-service`.

Goal for this phase:
- Service can start locally.
- Has basic health endpoints.
- Reads simple config from environment.
- Logs each request with a correlation ID in a structured, readable way.

No business logic (OCR/LLM/pipeline) is added yet.

---

## 1. Directory and files to create in Phase 0

Under `apps/idp-loan-deferment-service/` create:

- **Top level**
  - `PHASE_0_IMPLEMENTATION_PLAN.MD`  (this file)
  - `REPORT_3.MD`  (already exists)

- **App package**
  - `app/__init__.py`  (empty, just to make it a package)
  - `app/main.py`  – FastAPI application startup and router includes.
  - `app/api/__init__.py`
  - `app/api/v1/__init__.py`
  - `app/api/v1/routes_health.py` – `/health` and `/ready` endpoints.

- **Core utilities**
  - `app/core/__init__.py`
  - `app/core/config.py` – basic settings (e.g. service name, log level, runs dir).
  - `app/core/logging.py` – logging setup and correlation ID middleware.

You do **not** need `routes_process.py`, pipeline code, or clients in Phase 0.

---

## 2. `app/core/config.py` – minimal configuration

Purpose: central place to read environment variables and provide defaults.

Suggested content (conceptual):
- Define a `Settings` class (using Pydantic `BaseSettings` if available, or a simple class) with fields like:
  - `APP_NAME` – e.g. `"idp-loan-deferment-service"`.
  - `ENV` – `"dev"` / `"stage"` / `"prod"` (default `"dev"`).
  - `LOG_LEVEL` – e.g. `"INFO"`.
  - `RUNS_DIR` – default to `./runs` inside this project.
- Provide a `get_settings()` function that returns a singleton instance.

For Phase 0 we only actually **use**:
- `APP_NAME`
- `LOG_LEVEL`

We will use `RUNS_DIR` later when we implement the pipeline.

---

## 3. `app/core/logging.py` – logging and correlation IDs

Goals:
- Use Python `logging` with a consistent format.
- Attach a **request ID** (correlation ID) to each incoming HTTP request so you can trace logs for a single call.

Implementation steps:

1. **Basic logger configuration**
   - In `logging.py`, configure `logging.basicConfig` with:
     - Level from settings (`LOG_LEVEL`).
     - Format string that includes time, level, logger name, and `request_id` placeholder where possible.
   - Example format (conceptual):
     - `"%(asctime)s | %(levelname)s | %(name)s | %(message)s"`

2. **Request ID middleware**
   - In `logging.py`, define a FastAPI/Starlette middleware:
     - On each request:
       - Try to read `X-Request-ID` header from the client.
       - If not present, generate a new UUID.
       - Store it in `request.state.request_id`.
       - Optionally expose it as `X-Request-ID` response header.
   - You can also use `contextvars` to attach `request_id` into logging records, but for Phase 0 it’s enough to log it manually where needed.

3. **Helper to get logger**
   - Provide a `get_logger(name: str)` function that returns a configured logger.

In Phase 0 we will:
- Log at startup that the app is up.
- Log incoming requests in health endpoints with their `request_id`.

---

## 4. `app/api/v1/routes_health.py` – health & readiness endpoints

Purpose: simple endpoints to confirm that the service is running.

Endpoints:

- `GET /health`
  - Returns a small JSON indicating that the process is alive.
  - Example response:
    ```json
    { "status": "ok", "service": "idp-loan-deferment-service" }
    ```

- `GET /ready`
  - Indicates the service is **ready** to accept traffic.
  - For Phase 0, this can be the same as `/health`.
  - Later we can extend it to check DB connections, external dependencies, etc.

Implementation steps:

1. Import `FastAPI`/`APIRouter` and the logger helper.
2. Create an `APIRouter` instance, e.g. `router = APIRouter(prefix="", tags=["health"])`.
3. Add two route functions:
   - `@router.get("/health")`
   - `@router.get("/ready")`
4. In each function:
   - Get logger.
   - Optionally read `request.state.request_id` and include it in logs.
   - Return a small JSON dict with `status` and `service`.

---

## 5. `app/main.py` – FastAPI app entrypoint

Goals:
- Create the `FastAPI` app instance.
- Include the health router.
- Register the logging middleware.

Implementation steps:

1. **Create app instance**
   - Import `FastAPI` and `get_settings()`.
   - Create `app = FastAPI(title=settings.APP_NAME)`.

2. **Include routers**
   - Import `router` from `app.api.v1.routes_health`.
   - `app.include_router(router)`.

3. **Add middleware**
   - Import and add the request ID/logging middleware from `app.core.logging`.

4. **Startup/shutdown events (optional but useful)**
   - Add `@app.on_event("startup")` to log a message like:
     - `"Service started", env=..., log_level=...`.
   - Add `@app.on_event("shutdown")` to log that the service is stopping.

5. **Run command (for local dev)**
   - Document in this file or README:
     - `uvicorn app.main:app --reload` (with `cd` into `apps/idp-loan-deferment-service`).

---

## 6. How to test Phase 0

After implementing the files above:

1. **Start the service locally**
   - From `apps/idp-loan-deferment-service/`, run:
     - `uvicorn app.main:app --reload`

2. **Call health endpoints**
   - Open in browser or use curl:
     - `GET http://localhost:8000/health`
     - `GET http://localhost:8000/ready`
   - Expected: small JSON with `status: "ok"` and the service name.

3. **Check logs**
   - Confirm that:
     - Service startup is logged.
     - Each `/health` and `/ready` request is logged with some request ID.

If all of the above works, Phase 0 is complete and you can move to Phase 1 (add `/v1/process` and the real pipeline).
