import logging

from api.schemas import ProblemDetail
from core.utils import ensure_trace_id
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pipeline.core.exceptions import BaseError
from pydantic_core import ValidationError as PydanticCoreValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


async def handle_validation_error(request: Request, exc: RequestValidationError):
    """Handler for FastAPI/Pydantic request validation errors."""
    trace_id = ensure_trace_id(request)

    first_error = exc.errors()[0] if exc.errors() else {}
    loc = first_error.get("loc", [])
    field = ".".join(str(loc_part) for loc_part in loc if loc_part != "body")
    msg = first_error.get("msg", "Validation failed")
    detail = f"{field}: {msg}" if field else msg
    error_type = first_error.get("type", "")

    logger.warning(
        f"Validation error: {detail}",
        extra={"trace_id": trace_id, "field": field, "error_type": error_type},
    )

    problem = ProblemDetail(
        type="/errors/VALIDATION_ERROR",
        title="Request validation failed",
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=detail,
        instance=request.url.path,
        code="VALIDATION_ERROR",
        category="client_error",
        retryable=False,
        trace_id=trace_id,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=problem.dict(exclude_none=True),
        headers={"X-Trace-ID": trace_id},
    )


async def handle_pydantic_error(request: Request, exc: PydanticCoreValidationError):
    """Handler for generic Pydantic errors outside request validation."""
    trace_id = ensure_trace_id(request)

    logger.warning(
        "Pydantic validation failed",
        extra={
            "trace_id": trace_id,
            "path": request.url.path,
            "errors": str(exc.errors()),
        },
    )

    errors = exc.errors() if hasattr(exc, "errors") else []
    first_error = errors[0] if errors else {}
    msg = first_error.get("msg", "Validation failed")

    problem = ProblemDetail(
        type="/errors/VALIDATION_ERROR",
        title="Request validation failed",
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=msg,
        code="VALIDATION_ERROR",
        category="client_error",
        retryable=False,
        instance=request.url.path,
        trace_id=trace_id,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=problem.dict(exclude_none=True),
        headers={"X-Trace-ID": trace_id},
    )


async def handle_app_error(request: Request, exc: BaseError):
    """Handler for application-specific BaseErrors."""
    trace_id = ensure_trace_id(request)

    logger.error(
        "Application error occurred",
        extra={
            "trace_id": trace_id,
            "error_code": exc.error_code,
            "path": request.url.path,
            "http_status": exc.http_status,
        },
        exc_info=True,
    )

    problem = ProblemDetail(
        **exc.to_dict(),
        instance=request.url.path,
        trace_id=trace_id,
    )

    return JSONResponse(
        status_code=exc.http_status,
        content=problem.dict(exclude_none=True),
        headers={"X-Trace-ID": trace_id},
    )


async def handle_http_error(request: Request, exc: StarletteHTTPException):
    """Handler for standard HTTP exceptions (404, 401, etc.)."""
    trace_id = ensure_trace_id(request)

    logger.warning(
        "HTTP exception",
        extra={
            "trace_id": trace_id,
            "status_code": exc.status_code,
            "detail": exc.detail,
        },
    )

    problem = ProblemDetail(
        type=f"/errors/HTTP_{exc.status_code}",
        title=str(exc.detail),
        status=exc.status_code,
        detail=str(exc.detail),
        code=f"HTTP_{exc.status_code}",
        category="server_error" if exc.status_code >= 500 else "client_error",
        retryable=False,
        instance=request.url.path,
        trace_id=trace_id,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=problem.dict(exclude_none=True),
        headers={"X-Trace-ID": trace_id},
    )


async def handle_unknown_error(request: Request, exc: Exception):
    """Handler for unexpected 500 errors."""
    trace_id = ensure_trace_id(request)

    logger.exception(
        "Unexpected error occurred",
        extra={
            "trace_id": trace_id,
            "path": request.url.path,
            "error_type": type(exc).__name__,
        },
    )

    problem = ProblemDetail(
        type="/errors/INTERNAL_SERVER_ERROR",
        title="Internal server error",
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred. Please contact support with trace ID.",
        code="INTERNAL_SERVER_ERROR",
        category="server_error",
        retryable=False,
        instance=request.url.path,
        trace_id=trace_id,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=problem.dict(exclude_none=True),
        headers={"X-Trace-ID": trace_id},
    )
