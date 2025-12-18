"""FastAPI application entry point."""

from fastapi import (
    FastAPI,
    File,
    UploadFile,
    Form,
    Request,
    status,
    Depends,
    BackgroundTasks,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from api.schemas import (
    VerifyResponse,
    KafkaEventRequest,
    KafkaEventQueryParams,
    ProblemDetail,
    HealthResponse,
)
from api.validators import validate_upload_file, VerifyRequest
from api.middleware.exception_handler import exception_middleware
from services.processor import DocumentProcessor
from pipeline.core.logging_config import configure_structured_logging
from pipeline.utils.db_client import insert_verification_run
from pipeline.utils.io_utils import read_json as util_read_json
from minio.error import S3Error
import tempfile
import logging
import time
import uuid
import os

from dotenv import load_dotenv

load_dotenv()

configure_structured_logging(level="INFO", json_format=True)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown tasks."""
    from pipeline.core.db_config import get_db_pool, close_db_pool

    logger.info("🚀 Initializing database connection pool...")
    try:
        pool = await get_db_pool()
        logger.info("✅ Database pool ready")
    except Exception as e:
        logger.error(f"⚠️  Database pool initialization failed: {e}", exc_info=True)
        logger.warning("Application will continue without database connectivity")

    yield

    logger.info("🛑 Closing database connection pool...")
    await close_db_pool()
    logger.info("✅ Database pool closed")


# Initialize FastAPI app
app = FastAPI(
    title="RB-OCR Document Verification API",
    version="1.0.0",
    description="Validates loan deferment documents",
    docs_url="/docs",
    redoc_url="/redoc",
    root_path="/rb-ocr/api",
    lifespan=lifespan,
)


# ============================================================================
# Custom OpenAPI Schema (Remove HTTPValidationError)
# ============================================================================


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Remove the default validation error schemas if they exist
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

app.middleware("http")(exception_middleware)


# ============================================================================
# Validation Handler Helper Functions
# ============================================================================


def _ensure_trace_id(request: Request) -> str:
    """Ensure trace_id exists on request state."""
    trace_id = getattr(request.state, "trace_id", None)
    if not trace_id:
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id
    return trace_id


def _parse_validation_error(exc: RequestValidationError) -> tuple[str, str, str]:
    """Parse first validation error into field, detail, and error type."""
    first_error = exc.errors()[0] if exc.errors() else {}
    loc = first_error.get("loc", [])
    field = ".".join(str(loc_part) for loc_part in loc if loc_part != "body")
    msg = first_error.get("msg", "Validation failed")
    detail = f"{field}: {msg}" if field else msg
    error_type = first_error.get("type", "")
    return field, detail, error_type


def _build_validation_problem(
    request: Request, detail: str, trace_id: str
) -> ProblemDetail:
    """Build ProblemDetail for validation error."""
    return ProblemDetail(
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Convert Pydantic validation errors to RFC 7807 Problem Details format."""
    trace_id = _ensure_trace_id(request)
    field, detail, error_type = _parse_validation_error(exc)

    logger.warning(
        f"Validation error: {detail}",
        extra={"trace_id": trace_id, "field": field, "error_type": error_type},
    )

    problem = _build_validation_problem(request, detail, trace_id)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=problem.dict(exclude_none=True),
        headers={"X-Trace-ID": trace_id},
    )


# ============================================================================
# Shared Endpoint Helper Functions
# ============================================================================


async def _save_upload_to_temp(file: UploadFile) -> str:
    """Save uploaded file to temporary location."""
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=f"_{file.filename}"
    ) as temp_file:
        content = await file.read()
        temp_file.write(content)
        return temp_file.name


def _build_verify_response(
    result: dict,
    processing_time: float,
    trace_id: str,
    request_id: int | None = None,
) -> VerifyResponse:
    """Build VerifyResponse from pipeline result."""
    return VerifyResponse(
        request_id=request_id,
        run_id=result["run_id"],
        verdict=result["verdict"],
        errors=result["errors"],
        processing_time_seconds=round(processing_time, 2),
        trace_id=trace_id,
    )


def _queue_db_insert(background_tasks: BackgroundTasks, result: dict) -> None:
    """Queue database insert as background task."""
    try:
        final_json_path = result.get("final_result_path")
        if final_json_path:
            final_json = util_read_json(final_json_path)
            background_tasks.add_task(insert_verification_run, final_json)
    except Exception as e:
        logger.error(f"Failed to queue DB insert task: {e}", exc_info=True)


def _build_external_metadata(event: KafkaEventRequest, trace_id: str) -> dict:
    """Build external metadata dict from Kafka event."""
    return {
        "trace_id": trace_id,
        "external_request_id": str(event.request_id),
        "external_s3_path": event.s3_path,
        "external_iin": str(event.iin),
        "external_first_name": event.first_name,
        "external_last_name": event.last_name,
        "external_second_name": event.second_name,
    }


processor = DocumentProcessor(runs_root="./runs")


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """
    Combined health check
    Checks:
    - App responsiveness
    - Database connectivity
    """
    from pipeline.core.db_config import check_db_health

    db_health = await check_db_health()
    status_code = 200 if db_health["healthy"] else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if db_health["healthy"] else "unhealthy",
            "service": "rb-ocr-api",
            "version": "1.0.0",
            "database": {
                "status": "connected" if db_health["healthy"] else "disconnected",
                "latency_ms": db_health.get("latency_ms"),
                "error": db_health.get("error"),
            },
        },
    )


@app.post("/v1/verify", response_model=VerifyResponse, tags=["manual-verification"])
async def verify_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF or Image file"),
    fio: str = Form(..., description="Applicant's full name (FIO)"),
):
    """
    Verify a loan deferment document.

    Returns:
    - run_id: Unique identifier for this request
    - verdict: True if all checks pass, False otherwise
    - errors: List of failed checks (empty if verdict=True)
    - processing_time_seconds: Total processing duration
    - trace_id: Distributed tracing correlation ID
    """
    start_time = time.time()
    trace_id = getattr(request.state, "trace_id", None)

    logger.info(
        f"[NEW REQUEST] FIO={fio}, file={file.filename}", extra={"trace_id": trace_id}
    )

    # Validate input
    await validate_upload_file(file)
    verify_req = VerifyRequest(fio=fio)

    # Save and process
    tmp_path = await _save_upload_to_temp(file)
    try:
        result = await processor.process_document(
            file_path=tmp_path,
            original_filename=file.filename,
            fio=verify_req.fio,
        )

        processing_time = time.time() - start_time
        response = _build_verify_response(result, processing_time, trace_id)

        logger.info(
            f"[RESPONSE] run_id={response.run_id}, verdict={response.verdict}, time={response.processing_time_seconds}s, errors={response.errors}",
            extra={
                "trace_id": trace_id,
                "run_id": response.run_id,
                "errors": response.errors,
            },
        )

        _queue_db_insert(background_tasks, result)
        return response

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.post(
    "/v1/kafka/verify",
    response_model=VerifyResponse,
    tags=["kafka-integration"],
    summary="Verify document from Kafka event",
    description="Process document verification request from Kafka event with S3 path",
    responses={
        200: {
            "description": "Document verification completed (success or business validation failed)",
            "content": {
                "application/json": {
                    "examples": {
                        "success": {
                            "summary": "Verification successful",
                            "value": {
                                "run_id": "550e8400-e29b-41d4-a716-446655440000",
                                "verdict": True,
                                "errors": [],
                                "processing_time_seconds": 4.2,
                                "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                            },
                        },
                        "business_error": {
                            "summary": "Business validation failed",
                            "value": {
                                "run_id": "550e8400-e29b-41d4-a716-446655440001",
                                "verdict": False,
                                "errors": [{"code": "FIO_MISMATCH"}],
                                "processing_time_seconds": 4.5,
                                "trace_id": "b1c2d3e4-f5g6-7890-bcde-fg1234567890",
                            },
                        },
                    }
                }
            },
        },
        404: {
            "description": "S3 file not found",
            "model": ProblemDetail,
            "content": {
                "application/json": {
                    "example": {
                        "type": "/errors/RESOURCE_NOT_FOUND",
                        "title": "S3 object not found",
                        "status": 404,
                        "instance": "/rb-ocr/api/v1/kafka/verify",
                        "code": "RESOURCE_NOT_FOUND",
                        "category": "client_error",
                        "retryable": False,
                        "trace_id": "c1d2e3f4-g5h6-7890-cdef-gh1234567890",
                    }
                }
            },
        },
        422: {
            "description": "Request validation failed",
            "model": ProblemDetail,
            "content": {
                "application/json": {
                    "example": {
                        "type": "/errors/VALIDATION_ERROR",
                        "title": "Request validation failed",
                        "status": 422,
                        "detail": "iin: IIN must contain only digits",
                        "instance": "/rb-ocr/api/v1/kafka/verify",
                        "code": "VALIDATION_ERROR",
                        "category": "client_error",
                        "retryable": False,
                        "trace_id": "d1e2f3g4-h5i6-7890-defg-hi1234567890",
                    }
                }
            },
        },
        500: {
            "description": "Internal server error",
            "model": ProblemDetail,
            "content": {
                "application/json": {
                    "example": {
                        "type": "/errors/INTERNAL_SERVER_ERROR",
                        "title": "Internal server error",
                        "status": 500,
                        "detail": "An unexpected error occurred. Please contact support with trace ID.",
                        "instance": "/rb-ocr/api/v1/kafka/verify",
                        "code": "INTERNAL_SERVER_ERROR",
                        "category": "server_error",
                        "retryable": False,
                        "trace_id": "e1f2g3h4-i5j6-7890-efgh-ij1234567890",
                    }
                }
            },
        },
        502: {
            "description": "External service error (S3, OCR, LLM)",
            "model": ProblemDetail,
            "content": {
                "application/json": {
                    "example": {
                        "type": "/errors/S3_ERROR",
                        "title": "S3 service error",
                        "status": 502,
                        "instance": "/rb-ocr/api/v1/kafka/verify",
                        "code": "S3_ERROR",
                        "category": "server_error",
                        "retryable": True,
                        "trace_id": "f1g2h3i4-j5k6-7890-fghi-jk1234567890",
                    }
                }
            },
        },
    },
)
async def verify_kafka_event(
    request: Request,
    background_tasks: BackgroundTasks,
    event: KafkaEventRequest,
):
    """
    Process a Kafka event for document verification.

    This endpoint:
    1. Receives the Kafka event body with S3 file reference
    2. Validates all input fields (request_id, IIN, S3 path, names)
    3. Builds FIO from name components
    4. Downloads the document from S3 and runs verification pipeline
    5. Returns the same response format as /v1/verify

    Args:
        event: Kafka event body containing request_id, s3_path, iin, and name fields

    Returns:
        VerifyResponse with run_id, verdict, errors, processing_time_seconds, and trace_id
    """
    start_time = time.time()
    trace_id = getattr(request.state, "trace_id", None)

    logger.info(
        f"[NEW KAFKA EVENT] request_id={event.request_id}, "
        f"s3_path={event.s3_path}, iin={event.iin}",
        extra={"trace_id": trace_id, "request_id": event.request_id},
    )

    external_data = _build_external_metadata(event, trace_id)
    result = await processor.process_kafka_event(
        event_data=event.dict(),
        external_metadata=external_data,
    )

    processing_time = time.time() - start_time
    response = _build_verify_response(
        result, processing_time, trace_id, request_id=event.request_id
    )

    logger.info(
        f"[KAFKA RESPONSE] request_id={event.request_id}, "
        f"run_id={response.run_id}, verdict={response.verdict}, "
        f"time={response.processing_time_seconds}s, errors={response.errors}",
        extra={
            "trace_id": trace_id,
            "request_id": event.request_id,
            "run_id": response.run_id,
            "errors": response.errors,
        },
    )

    _queue_db_insert(background_tasks, result)
    return response


# ============================================================================
# The following endpoint uses GET with side effects (document processing).
# This violates REST principles where GET should be idempotent and safe.
# Best Practice: Use POST /v1/kafka/verify instead.
# ============================================================================


@app.get(
    "/v1/kafka/verify-get",
    response_model=VerifyResponse,
    tags=["kafka-integration"],
    summary="Verify document from Kafka event",
    description="Process document verification request using query parameters instead of JSON body.",
    responses={
        200: {
            "description": "Document verification completed (success or business validation failed)",
            "content": {
                "application/json": {
                    "examples": {
                        "success": {
                            "summary": "Verification successful",
                            "value": {
                                "run_id": "550e8400-e29b-41d4-a716-446655440000",
                                "verdict": True,
                                "errors": [],
                                "processing_time_seconds": 4.2,
                                "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                            },
                        },
                        "business_error": {
                            "summary": "Business validation failed",
                            "value": {
                                "run_id": "550e8400-e29b-41d4-a716-446655440001",
                                "verdict": False,
                                "errors": [{"code": "FIO_MISMATCH"}],
                                "processing_time_seconds": 4.5,
                                "trace_id": "b1c2d3e4-f5g6-7890-bcde-fg1234567890",
                            },
                        },
                    }
                }
            },
        },
        404: {
            "description": "S3 file not found",
            "model": ProblemDetail,
            "content": {
                "application/json": {
                    "example": {
                        "type": "/errors/RESOURCE_NOT_FOUND",
                        "title": "S3 object not found",
                        "status": 404,
                        "instance": "/rb-ocr/api/v1/kafka/verify-get",
                        "code": "RESOURCE_NOT_FOUND",
                        "category": "client_error",
                        "retryable": False,
                        "trace_id": "c1d2e3f4-g5h6-7890-cdef-gh1234567890",
                    }
                }
            },
        },
        422: {
            "description": "Request validation failed",
            "model": ProblemDetail,
            "content": {
                "application/json": {
                    "example": {
                        "type": "/errors/VALIDATION_ERROR",
                        "title": "Request validation failed",
                        "status": 422,
                        "detail": "iin: IIN must contain only digits",
                        "instance": "/rb-ocr/api/v1/kafka/verify-get",
                        "code": "VALIDATION_ERROR",
                        "category": "client_error",
                        "retryable": False,
                        "trace_id": "d1e2f3g4-h5i6-7890-defg-hi1234567890",
                    }
                }
            },
        },
        500: {
            "description": "Internal server error",
            "model": ProblemDetail,
            "content": {
                "application/json": {
                    "example": {
                        "type": "/errors/INTERNAL_SERVER_ERROR",
                        "title": "Internal server error",
                        "status": 500,
                        "detail": "An unexpected error occurred. Please contact support with trace ID.",
                        "instance": "/rb-ocr/api/v1/kafka/verify-get",
                        "code": "INTERNAL_SERVER_ERROR",
                        "category": "server_error",
                        "retryable": False,
                        "trace_id": "e1f2g3h4-i5j6-7890-efgh-ij1234567890",
                    }
                }
            },
        },
        502: {
            "description": "External service error (S3, OCR, LLM)",
            "model": ProblemDetail,
            "content": {
                "application/json": {
                    "example": {
                        "type": "/errors/S3_ERROR",
                        "title": "S3 service error",
                        "status": 502,
                        "instance": "/rb-ocr/api/v1/kafka/verify-get",
                        "code": "S3_ERROR",
                        "category": "server_error",
                        "retryable": True,
                        "trace_id": "f1g2h3i4-j5k6-7890-fghi-jk1234567890",
                    }
                }
            },
        },
    },
)
async def verify_kafka_event_get(
    request: Request,
    background_tasks: BackgroundTasks,
    params: KafkaEventQueryParams = Depends(),
):
    """
    Process a Kafka event for document verification using query parameters.

    This is a GET equivalent of the POST /v1/kafka/verify endpoint.
    Uses the same helper functions for consistency.

    Args:
        request: FastAPI request object
        params: Query parameters validated as KafkaEventQueryParams

    Returns:
        VerifyResponse with run_id, verdict, errors, processing_time_seconds, and trace_id
    """
    start_time = time.time()
    trace_id = getattr(request.state, "trace_id", None)

    logger.info(
        f"[NEW KAFKA EVENT (GET)] request_id={params.request_id}, "
        f"s3_path={params.s3_path}, iin={params.iin}",
        extra={"trace_id": trace_id, "request_id": params.request_id},
    )

    # Convert params to KafkaEventRequest for metadata building
    event = KafkaEventRequest(**params.dict())
    external_data = _build_external_metadata(event, trace_id)

    result = await processor.process_kafka_event(
        event_data=params.dict(),
        external_metadata=external_data,
    )

    processing_time = time.time() - start_time
    response = _build_verify_response(
        result, processing_time, trace_id, request_id=params.request_id
    )

    logger.info(
        f"[KAFKA RESPONSE (GET)] request_id={params.request_id}, "
        f"run_id={response.run_id}, verdict={response.verdict}, "
        f"time={response.processing_time_seconds}s",
        extra={
            "trace_id": trace_id,
            "request_id": params.request_id,
            "run_id": response.run_id,
        },
    )

    _queue_db_insert(background_tasks, result)
    return response
