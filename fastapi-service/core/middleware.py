from fastapi import Request
from core.utils import ensure_trace_id


async def trace_id_middleware(request: Request, call_next):
    """
    Middleware that ensures every request has a Trace ID.

    1. Generates or retrieves Trace ID.
    2. Adds it to Request State (for access in endpoints/loggers).
    3. Adds it to Response Headers (for client visibility).
    """
    # 1. Ensure Trace ID (Get from header or generate new)
    # We use ensure_trace_id to handle the logic centrally
    trace_id = ensure_trace_id(request)

    # 2. Process Request
    response = await call_next(request)

    # 3. Add to Response Headers
    response.headers["X-Trace-ID"] = trace_id

    return response
