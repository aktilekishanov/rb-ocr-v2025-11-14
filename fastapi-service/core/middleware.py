"""Request tracing middleware."""

import uuid

from fastapi import Request


def _ensure_trace_id(request: Request) -> str:
    """Get or generate trace ID for request."""
    trace_id = getattr(request.state, "trace_id", None)
    if not trace_id:
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id
    return trace_id


async def trace_id_middleware(request: Request, call_next):
    """Ensure every request has a trace ID in state and response headers."""
    trace_id = _ensure_trace_id(request)
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response
