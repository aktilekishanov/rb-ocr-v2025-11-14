# Phase 0 – Detailed Explanation

This document explains **every part** created in Phase 0 of `idp-loan-deferment-service`:
- What it is
- Why it is needed
- How it works (at a high level, but precisely)

Phase 0 scope: **FastAPI skeleton**, health endpoints, config, logging with request IDs, and requirements. No business pipeline logic yet.

---

## 0. Key terms (quick glossary)

- **FastAPI**  
  A Python framework for building web APIs (Application Programming Interfaces). It lets us define HTTP endpoints like `/health` and `/v1/process` using Python functions.

- **ASGI (Asynchronous Server Gateway Interface)**  
  A standard way for Python web servers and frameworks to talk to each other, designed for asynchronous code. FastAPI apps speak ASGI.

- **uvicorn**  
  A high‑performance ASGI web server. It runs the FastAPI application and listens for HTTP requests, for example when we run `uvicorn app.main:app --reload`.

- **Environment variable**  
  A key–value setting (like `IDP_LOG_LEVEL=DEBUG`) provided by the operating system. We use them to configure the service without changing code.

- **Middleware**  
  A piece of code that runs **before and after** each HTTP request. Here we use middleware to attach a request identifier (`request_id`) and add it to logs.

- **Router / endpoint**  
  A *router* groups related endpoints. An *endpoint* is a specific URL + HTTP method (for example, `GET /health`) implemented by a Python function.

- **Request ID (request identifier)**  
  A unique identifier for each HTTP request. We put it in logs so we can trace all log lines that belong to the same request.

---

## 1. Project root: `idp-loan-deferment-service/`

This directory is the **root folder of the new standalone service**. It is independent from `main-dev`.

### 1.1 `requirements.txt`

**What it is**  
A list of Python libraries the service needs.

**Why needed**  
So that we can install exactly the packages required to run the FastAPI service.

**What’s inside & how it works**
- `fastapi>=0.110,<1.0`
  - The main web framework. Gives us `FastAPI`, routing, request/response handling, dependency injection, etc.
- `uvicorn[standard]>=0.23,<1.0`
  - ASGI (Asynchronous Server Gateway Interface) server used to run FastAPI. `uvicorn app.main:app --reload` starts the service.
- `pydantic>=2.4,<3.0`
  - For data validation and settings. Even if Phase 0 doesn’t use models heavily, later phases will.
- `pydantic-settings>=2.0,<3.0`
  - A helper library to build configuration classes driven by environment variables.

When you run `pip install -r requirements.txt`, these dependencies are installed.

---

## 2. Python package structure: `app/`

`app` is the **Python package** that holds all the service code.

### 2.1 `app/__init__.py`

**What it is**  
An empty file that tells Python "this directory is a package".

**Why needed**  
So that imports like `from app.core.config import get_settings` work.

**How it works**  
Python sees `__init__.py` and allows `app` to be imported as a module.

---

## 3. Core configuration: `app/core/`

This folder holds **core utilities** shared across the service.

### 3.1 `app/core/__init__.py`

Same idea as `app/__init__.py`: marks `core` as a subpackage.

### 3.2 `app/core/config.py`

**What it is**  
Central configuration module. Defines a `Settings` object and a `get_settings()` helper.

**Why needed**  
To read environment variables (like log level, environment, and runs directory) in a **single, consistent place**, and to avoid scattering `os.getenv(...)` calls across the codebase.

**How it works (step by step)**

- Tries to import `BaseSettings` and `Field` from `pydantic-settings` / `pydantic`.
  - If imports succeed:
    - Defines a `Settings(BaseSettings)` class with fields:
      - `APP_NAME` – default: `"idp-loan-deferment-service"`.
      - `ENVIRONMENT` – default: `"dev"`.
      - `LOG_LEVEL` – default: `"INFO"`.
      - `RUNS_DIR` – default: a **service-local `runs/` folder**.
    - Uses `env_prefix = "IDP_"`, so environment variables like `IDP_LOG_LEVEL` override defaults.
  - If imports fail (for example, `pydantic-settings` not installed):
    - Defines a minimal fallback `Settings` class that reads environment variables using `os.getenv`.

- `_default_runs_dir()` helper (in the pydantic-based branch):
  - Builds a path: `Path(__file__).resolve().parents[2] / "runs"`.
  - This resolves to `<project-root>/runs` inside `idp-loan-deferment-service`.

- `get_settings()` function:
  - Decorated with `@lru_cache(maxsize=1)`: ensures **only one Settings instance** is created.
  - Any call `get_settings()` returns the same object (cheap and consistent).

**Why RUNS_DIR matters**  
Even though Phase 0 doesn’t write artifacts, later phases (pipeline) will store per-run files under `RUNS_DIR`. Defining it now prepares the service for that, and ensures all code uses the same base directory.

---

## 4. Logging and request identifiers: `app/core/logging.py`

This module sets up **logging** and a **request ID middleware** that is safe for asynchronous/concurrency use.

### 4.1 Context variable `_request_id_ctx`

**What it is**  
A `contextvars.ContextVar` that stores the current `request_id` for the active request.

**Why needed**  
In asynchronous code, there can be many requests being handled in parallel. A global variable would mix them up. `ContextVar` allows each request to carry its own identifier across `await` boundaries.

**How it works**  
- `_request_id_ctx` is created with default value `"-"`.
- When a request comes in, the middleware sets `_request_id_ctx` to that request's ID.
- Log filters can then read `_request_id_ctx.get()` and attach it to each log record.

### 4.2 `get_request_id()`

A small helper to return the current request ID from `_request_id_ctx`.

### 4.3 `RequestIdFilter`

**What it is**  
A `logging.Filter` subclass that injects `request_id` into every log record.

**Why needed**  
So log messages can include `request_id=...` without each log call manually passing it.

**How it works**  
- `filter(self, record)` is called by the logging system for each record.
- It sets `record.request_id = get_request_id()`.
- The `logging.Formatter` can then use `%(request_id)s` in its format string.

### 4.4 `configure_logging(level: str)`

**What it is**  
A function to set up the **root logger**.

**Why needed**  
To consistently format logs and ensure that they go to stdout with the right level and include a request ID.

**How it works**  
- Gets the root logger with `logging.getLogger()` and sets its level.
- Removes any existing handlers to avoid duplicate logs (important when using `--reload`).
- Creates a `StreamHandler` pointing to `sys.stdout`.
- Attaches `RequestIdFilter` to the handler.
- Sets a formatter with format:
  - `"%(asctime)s | %(levelname)s | %(name)s | request_id=%(request_id)s | %(message)s"`
- Adds the handler to the root logger.

### 4.5 `get_logger(name: str)`

A thin wrapper around `logging.getLogger(name)`.

**Why needed**  
So that other modules import `get_logger` from a single place.

### 4.6 `RequestIdMiddleware`

**What it is**  
A Starlette/FastAPI middleware class (inherits from `BaseHTTPMiddleware`) that:
- Ensures every request has a `request_id`.
- Stores it in both `request.state.request_id` and the `ContextVar` used in logging.
- Echoes the `X-Request-ID` header back in the response.

**Why needed**
- **Correlation**: To easily tie together logs from the same request.
- **Async-safety**: Works correctly even with many concurrent requests.

**How it works (step by step)**
- `dispatch(self, request, call_next)` is called for each request:
  1. Reads `X-Request-ID` from the incoming headers, if present.
  2. If missing, generates a new UUID (`uuid.uuid4().hex`).
  3. Stores it on `request.state.request_id`.
  4. Calls `_request_id_ctx.set(rid)` and saves the token.
  5. Calls `response = await call_next(request)` to let the rest of the app handle the request.
  6. Sets `response.headers["X-Request-ID"] = rid`.
  7. In a `finally` block, resets the context variable with `_request_id_ctx.reset(token)`.

Because each request sets its own value in a context variable, logs remain correct in asynchronous and concurrent scenarios – this is why we say **"Logging includes a RequestIdMiddleware and is safe for asynchronous/concurrency use."**

---

## 5. Health API: `app/api/v1/routes_health.py`

This module exposes the Phase 0 endpoints `/health` and `/ready`.

### 5.1 Router setup

**What it is**  
Defines `router = APIRouter(tags=["health"])` and two routes.

**Why needed**  
- `/health` and `/ready` are standard endpoints that external systems and operators use to check if the service is up.
- They will later be used by Kubernetes or other orchestration tools for liveness/readiness probes.

### 5.2 `/health` endpoint

**What it is**  
- `@router.get("/health")` async function.

**How it works**
- Accepts a `Request` object.
- Fetches settings via `get_settings()`.
- Gets a logger with `get_logger(__name__)`.
- Logs a simple info message (`"health"`) including the request path.
- Returns a JSON object like:
  - `{ "status": "ok", "service": settings.APP_NAME }`.

This indicates that the process is alive.

### 5.3 `/ready` endpoint

**What it is**  
- `@router.get("/ready")` async function.

**How it works**
- Similar to `/health`:
  - Logs a `"ready"` event.
  - Returns the same JSON structure.
- In Phase 0, readiness is the same as liveness. Later, we can add real checks (for example, database connection, external dependency health).

---

## 6. Main application: `app/main.py`

This is the **entrypoint** FastAPI uses.

### 6.1 Settings and logging initialization

**What it is**  
Top of the file:
- Imports `FastAPI`.
- Imports the health router, settings, and logging utilities.
- Calls `settings = get_settings()`.
- Calls `configure_logging(settings.LOG_LEVEL)` **once** at import time.

**Why needed**  
- Ensures logging is configured **before** the app starts handling requests.
- Ensures all modules share the same configuration.

### 6.2 `app = FastAPI(title=settings.APP_NAME)`

**What it is**  
The global ASGI application object that uvicorn will run.

**Why needed**  
- uvicorn expects something like `app.main:app` to point to a FastAPI instance.
- `title` is used for documentation and introspection.

### 6.3 Middleware registration

```python
app.add_middleware(RequestIdMiddleware)
```

**What it is**  
Registers the request ID middleware described earlier.

**How it works**  
Every request goes through this middleware; a request ID is attached, and logs get the correct `request_id` value.

### 6.4 Router inclusion

```python
app.include_router(health_router)
```

**What it is**  
Attaches the `/health` and `/ready` routes to the application.

**How it works**  
FastAPI merges the routes defined in `health_router` into the main app’s routing table.

### 6.5 Startup and shutdown events

```python
@app.on_event("startup")
async def on_startup():
    logger = get_logger(__name__)
    logger.info("service_startup", extra={"environment": settings.ENVIRONMENT, "log_level": settings.LOG_LEVEL})

@app.on_event("shutdown")
async def on_shutdown():
    logger = get_logger(__name__)
    logger.info("service_shutdown")
```

**What it is**  
Lifecycle hooks that run when the service starts and stops.

**Why needed**  
- To log clear messages during startup/shutdown.
- Later, we can add resource initialization/cleanup here (e.g., database connections).

**How it works**  
- When uvicorn starts the app, it triggers the `startup` event: logs "service_startup" with environment and log level.
- When uvicorn stops, it triggers `shutdown`: logs "service_shutdown".

---

## 7. How RUNS_DIR and RequestIdMiddleware fit into future phases

### 7.1 RUNS_DIR

- **Defined in**: `app/core/config.py` as `settings.RUNS_DIR`.
- **Default**: `<service-root>/runs` (e.g., `apps/idp-loan-deferment-service/runs`).
- **Purpose**: Base directory where we will later create per-run folders like:
  - `runs/YYYY-MM-DD/<run_id>/...`
- **Why define now**:
  - Keeps all file paths centralized.
  - Makes it trivial to switch to a different path or mount (e.g., shared volume) via `IDP_RUNS_DIR` environment variable.

### 7.2 RequestIdMiddleware and asynchronous/concurrency safety

- In FastAPI, each HTTP request is handled in an asynchronous function.
- Multiple requests can be processed at the same time (concurrently).
- If we used a simple global variable for `request_id`, we’d get incorrect mixing between requests.
- By using:
  - **ContextVar** (`_request_id_ctx`)
  - **BaseHTTPMiddleware** to set/reset the context for each request
- We ensure that each log line for a request uses **that request’s identifier** only, even when there are many concurrent requests.

This is why we can say: **"Logging includes a RequestIdMiddleware and is safe for asynchronous/concurrency use."**

---

## 8. Summary

Phase 0 created a clean, production-style skeleton:
- Standalone FastAPI app with `/health` and `/ready`.
- Centralized, environment-driven configuration via `Settings` and `get_settings()`.
- Robust logging setup with request correlation identifiers, ready for concurrent traffic.
- A default `RUNS_DIR` pointing to a service-local `runs/` directory, which will be used later for pipeline artifacts.

This foundation follows modern backend best practices and is ready for Phase 1, where we will add the real `/v1/process` endpoint and document-processing pipeline.
