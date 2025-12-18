import uuid
from fastapi import Request


def ensure_trace_id(request: Request) -> str:
    """Ensure trace_id exists on request state."""
    trace_id = getattr(request.state, "trace_id", None)
    if not trace_id:
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id
    return trace_id
