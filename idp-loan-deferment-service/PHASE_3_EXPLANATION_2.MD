# Phase 3 – Additional Observability & Resilience Work (Follow‑ups)

This document covers **only the extra work** done after the initial Phase 3 implementation:
- Wiring job metrics counters.
- Adding metrics tests.
- Adding tracing stubs.
- Adding retry utilities.
- Refactoring startup/shutdown lifecycle and cleaning Pydantic config warnings.

It is meant to be read **after** `PHASE_3_EXPLANATION.MD`.

---

## 1. Job metrics wiring

### 1.1 What was added

File: `app/observability/metrics.py`
- Already had counters:
  - `jobs_submitted_total`
  - `jobs_completed_total`
  - `jobs_failed_total`
- Helper functions are now clearly intended for external use:
  - `inc_job_submitted()`
  - `inc_job_completed()`
  - `inc_job_failed()`

File: `app/services/jobs.py`
- We now **increment those counters** at the appropriate lifecycle points:
  - In `submit_job(...)`:
    - After `create_job_record(run_id)`, we call `inc_job_submitted()`.
  - In `set_completed(...)`:
    - After writing job status JSON, we call `inc_job_completed()`.
  - In `set_failed(...)`:
    - After writing job status JSON, we call `inc_job_failed()`.
- Each call is wrapped in a `try/except` so that if metrics are disabled or misconfigured, **job handling still works**.

### 1.2 Why this matters

- Now the metrics accurately reflect **how many jobs were submitted, completed, and failed**.
- This is aligned with the Phase 3 plan’s acceptance criteria:
  - “Job counters exist for submit/completion/failure.”
- It enables dashboards and alerts like:
  - “Job failure rate over last 15 minutes”.
  - “Total jobs per client per day” (with more labels later).

---

## 2. Metrics tests

### 2.1 What was added

File: `tests/test_metrics.py`

- New test `test_metrics_endpoint_exists_and_has_http_requests_total()`:
  - Uses `TestClient(app)` to:
    1. Call `/health` and `/ready` to generate some traffic.
    2. Call `/metrics`.
  - Asserts:
    - The `/metrics` endpoint returns HTTP 200.
    - The metrics text contains the `http_requests_total` series.
    - The metrics output contains path labels for `/health` and `/ready`.

### 2.2 Why this matters

- Confirms that observability wiring is **not just present in code, but actually working**.
- Guards against accidental removal or renaming of metrics.
- Provides a low‑cost safety net when refactoring routers or middleware.

---

## 3. Tracing stubs (optional OpenTelemetry)

### 3.1 What was added

File: `app/observability/tracing.py`

- New function `init_tracing_if_enabled(settings)`:
  - Reads `settings.TRACING_ENABLED`.
  - If `False`, it **returns immediately** (no tracing in dev by default).
  - If `True`, it tries to import OpenTelemetry components:
    - `opentelemetry.trace` and SDK pieces.
    - `opentelemetry.instrumentation.fastapi.FastAPIInstrumentor`.
  - If imports fail, it logs a warning and returns (no crash).
  - If imports succeed, it:
    - Creates a `TracerProvider` with a `Resource` tagged with `service.name`.
    - Attaches a `BatchSpanProcessor` with a `ConsoleSpanExporter` (dev‑friendly; real deployments can swap exporters).

- New function `instrument_app_if_tracing_enabled(app, settings)`:
  - Again checks `TRACING_ENABLED`.
  - Tries to import `FastAPIInstrumentor`.
  - If available, calls `FastAPIInstrumentor().instrument_app(app)`.
  - Logs success or a non‑fatal warning if something fails.

File: `app/core/config.py`

- Settings gained a new field:
  - `TRACING_ENABLED: bool`.
  - Backed by env var `IDP_TRACING_ENABLED`.
  - In the fallback (non‑Pydantic) implementation, values like `"true"`, `"1"`, `"yes"`, `"on"` are treated as **enabled**.

File: `app/main.py`

- Tracing is wired into FastAPI’s **lifespan** (see section 5) so there is a single consistent initialization point:
  - In the `lifespan(app)` function we call:
    - `init_tracing_if_enabled(settings)`
    - `instrument_app_if_tracing_enabled(app, settings)`
  - Both calls are wrapped in `try/except` so the app is robust even if tracing config or deps break.

### 3.2 Why this matters

- We now satisfy the Phase 3 acceptance criteria that **tracing hooks exist and are env‑gated**, without forcing any particular tracing backend in dev.
- When you later deploy in an environment with OpenTelemetry collectors and backends, you can:
  - Install the relevant OTel packages.
  - Set `IDP_TRACING_ENABLED=true`.
  - Reuse this code without touching business logic.

---

## 4. Retry utilities stub

### 4.1 What was added

File: `app/observability/retries.py`

- `retry(fn, *args, retries=2, backoff=0.2, max_backoff=1.0, exceptions=(Exception,), **kwargs)`:
  - Synchronous helper.
  - Executes `fn(*args, **kwargs)`.
  - On exception (matching `exceptions`):
    - Sleeps for `backoff` seconds.
    - Doubles the delay each attempt (exponential backoff) up to `max_backoff`.
    - Retries until attempts exceed `retries`, then re‑raises.

- `async_retry(fn, *args, retries=2, backoff=0.2, max_backoff=1.0, exceptions=(Exception,), **kwargs)`:
  - Async variant using `await fn(...)` and `asyncio.sleep(...)`.
  - Same backoff logic as the sync helper.

### 4.2 Why this matters

- Matches the Phase 3 plan’s description of a foundational retry utility:
  - Prepared, but **not yet wired** to any external systems (OCR/LLM, MinIO/S3, etc.).
- When those integrations are added in later phases, we can simply wrap network calls with these helpers instead of inventing retries from scratch.

---

## 5. Lifecycle & configuration refactors

### 5.1 FastAPI lifespan instead of on_event

File: `app/main.py`

**Before:**
- Used deprecated FastAPI decorators:
  - `@app.on_event("startup")`
  - `@app.on_event("shutdown")`
- Each handler logged startup/shutdown messages.

**After:**
- Introduced a **lifespan context manager**:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = get_logger(__name__)
    try:
        init_tracing_if_enabled(settings)
        instrument_app_if_tracing_enabled(app, settings)
    except Exception:
        pass

    logger.info("service_startup", extra={"env": settings.ENV, "log_level": settings.LOG_LEVEL})
    try:
        yield
    finally:
        logger.info("service_shutdown")

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
```

- Middlewares and routers are added as before:
  - `RequestIdMiddleware`
  - `MetricsMiddleware`
  - Health, process, jobs, and metrics routers.

**Why this matters:**
- Removes deprecation warnings from FastAPI.
- Gives a single, clear place to initialize cross‑cutting concerns (logging, tracing, metrics, etc.).

### 5.2 Pydantic settings migrated to V2 style

File: `app/core/config.py`

**Before:**
- Pydantic `Settings` class used an inner `Config` subclass to define `env_prefix`.
- This pattern is **deprecated** in Pydantic V2, which raised warnings.

**After:**
- Switched to the V2 style using `SettingsConfigDict`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IDP_")
    APP_NAME: str = Field(default="idp-loan-deferment-service")
    ENV: str = Field(default="dev")
    LOG_LEVEL: str = Field(default="INFO")
    RUNS_DIR: Path = Field(default_factory=_default_runs_dir)
    TRACING_ENABLED: bool = Field(default=False)
```

- The fallback (non‑Pydantic) `Settings` class already read the same env vars.

**Why this matters:**
- Removes Pydantic V2 deprecation warnings.
- Keeps settings consistent and future‑proof.

---

## 6. How this all ties back to the Phase 3 plan

- **Job metrics** – fully aligned with “Job counters exist for submit/completion/failure”.
- **Metrics tests** – implements the optional automated tests described in the plan.
- **Tracing stubs** – satisfy “Tracing hooks exist and are initialized only when enabled via env”, without forcing a particular tracing backend.
- **Retries** – provide the planned `retry` and `async_retry` utilities to be used in later phases.
- **Lifespan & config refactor** – not strictly required by the plan, but:
  - Remove deprecations.
  - Provide a cleaner, modern base for Phase 4 and beyond.

In short, these follow‑up changes **complete Phase 3** so that the implementation now matches the plan not only in spirit (observability and resilience) but also in concrete details (job metrics, retries, tracing hooks, tests, and modern lifecycle management).
