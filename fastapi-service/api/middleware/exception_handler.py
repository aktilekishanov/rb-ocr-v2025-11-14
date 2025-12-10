"""Global exception handling middleware.

This middleware catches all exceptions and converts them to structured
RFC 7807 Problem Details responses. It also adds trace IDs for request
correlation and distributed tracing.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic_core import ValidationError as PydanticCoreValidationError
import logging
import uuid
from http import HTTPStatus

from pipeline.core.exceptions import BaseError
from api.schemas import ProblemDetail

logger = logging.getLogger(__name__)


async def exception_middleware(request: Request, call_next):
    """Global exception handling middleware.
    
    Generates trace IDs, catches all exceptions, and returns structured
    RFC 7807 Problem Details responses.
    
    Args:
        request: FastAPI request object
        call_next: Next middleware/handler in chain
        
    Returns:
        Response with trace ID header
    """
    
    trace_id = str(uuid.uuid4())
    request.state.trace_id = trace_id
    
    try:
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response
    
    except BaseError as e:
        logger.error(
            "Application error occurred",
            extra={
                "trace_id": trace_id,
                "error_code": e.error_code,
                "path": request.url.path,
                "http_status": e.http_status,
            },
            exc_info=True
        )
        
        problem = ProblemDetail(
            **e.to_dict(),
            instance=request.url.path,
            trace_id=trace_id,
        )
        
        return JSONResponse(
            status_code=e.http_status,
            content=problem.dict(exclude_none=True),
            headers={"X-Trace-ID": trace_id}
        )
    
    except PydanticCoreValidationError as e:
        logger.warning(
            "Pydantic validation failed",
            extra={
                "trace_id": trace_id,
                "path": request.url.path,
                "errors": str(e.errors()),
            }
        )
        
        errors = e.errors() if hasattr(e, 'errors') else []
        first_error = errors[0] if errors else {}
        
        loc = first_error.get("loc", [])
        field = ".".join(str(loc_part) for loc_part in loc if loc_part != "body")
        msg = first_error.get("msg", "Validation failed")
        
        problem = ProblemDetail(
            type="/errors/VALIDATION_ERROR",
            title="Request validation failed",
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field}: {msg}" if field else msg,
            code="VALIDATION_ERROR",
            category="client_error",
            retryable=False,
            instance=request.url.path,
            trace_id=trace_id,
        )
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=problem.dict(exclude_none=True),
            headers={"X-Trace-ID": trace_id}
        )
    
    except RequestValidationError as e:
        logger.warning(
            "Request validation failed",
            extra={
                "trace_id": trace_id,
                "path": request.url.path,
                "errors": str(e.errors()),
            }
        )
        
        first_error = e.errors()[0] if e.errors() else {}
        field = ".".join(str(loc) for loc in first_error.get("loc", []))
        msg = first_error.get("msg", "Validation failed")
        
        problem = ProblemDetail(
            type="/errors/VALIDATION_ERROR",
            title="Request validation failed",
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field}: {msg}" if field else msg,
            code="VALIDATION_ERROR",
            category="client_error",
            retryable=False,
            instance=request.url.path,
            trace_id=trace_id,
        )
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=problem.dict(exclude_none=True),
            headers={"X-Trace-ID": trace_id}
        )
    
    except StarletteHTTPException as e:
        logger.warning(
            "HTTP exception",
            extra={
                "trace_id": trace_id,
                "status_code": e.status_code,
                "detail": e.detail,
            }
        )
        
        problem = ProblemDetail(
            type=f"/errors/HTTP_{e.status_code}",
            title=e.detail,
            status=e.status_code,
            detail=e.detail,
            code=f"HTTP_{e.status_code}",
            category="server_error" if e.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR else "client_error",
            retryable=False,
            instance=request.url.path,
            trace_id=trace_id,
        )
        
        return JSONResponse(
            status_code=e.status_code,
            content=problem.dict(exclude_none=True),
            headers={"X-Trace-ID": trace_id}
        )
    
    except Exception as e:
        logger.exception(
            "Unexpected error occurred",
            extra={
                "trace_id": trace_id,
                "path": request.url.path,
                "error_type": type(e).__name__,
            }
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
            headers={"X-Trace-ID": trace_id}
        )
