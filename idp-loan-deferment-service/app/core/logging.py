from __future__ import annotations

import logging
import sys
import uuid
import contextvars
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

# Context var to carry request_id across async tasks
_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id_ctx.get()


class RequestIdFilter(logging.Filter):
    """Inject request_id from contextvars into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 (shadow builtins)
        try:
            record.request_id = get_request_id()
        except Exception:  # pragma: no cover - defensive
            record.request_id = "-"
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging with a consistent, structured-ish format.

    Called once on application import/startup. Safe to call repeatedly.
    """
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Remove existing handlers to avoid duplicate logs in reload
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level.upper())
    handler.addFilter(RequestIdFilter())
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | request_id=%(request_id)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware to attach a request ID to each request/response.

    - Reads X-Request-ID header if provided; otherwise generates a UUID.
    - Stores value in request.state.request_id and a contextvar for logging.
    - Echoes header back in the response.
    """

    async def dispatch(self, request: Request, call_next):
        incoming: Optional[str] = request.headers.get("X-Request-ID")
        rid = incoming or uuid.uuid4().hex
        request.state.request_id = rid
        token = _request_id_ctx.set(rid)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            _request_id_ctx.reset(token)
