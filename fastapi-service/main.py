"""FastAPI application entry point."""
from fastapi import FastAPI, File, UploadFile, Form, Request, status, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from api.schemas import VerifyResponse, KafkaEventRequest, KafkaEventQueryParams, ProblemDetail
from api.validators import validate_upload_file, VerifyRequest
from api.middleware.exception_handler import exception_middleware
from services.processor import DocumentProcessor
from pipeline.core.logging_config import configure_structured_logging
from minio.error import S3Error  # Keep this import as it's used in /v1/kafka/verify
import tempfile
import logging
import time
import uuid
import os

# Configure structured JSON logging for production
configure_structured_logging(level="INFO", json_format=True)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="[DEV] RB-OCR Document Verification API",
    version="1.0.0",
    description="Validates loan deferment documents",
    docs_url="/docs",
    redoc_url="/redoc",
    root_path="/rb-ocr/api",
)

# Register global exception middleware
app.middleware("http")(exception_middleware)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Convert Pydantic validation errors to RFC 7807 Problem Details format.
    
    This handler ensures all validation errors follow the RFC 7807 standard,
    maintaining consistency with other error responses.
    
    Args:
        request: The FastAPI request object
        exc: The Pydantic validation error
        
    Returns:
        JSONResponse with RFC 7807 ProblemDetail format
    """
    # Get or generate trace_id
    trace_id = getattr(request.state, "trace_id", None)
    if not trace_id:
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id
    
    # Extract first validation error for main message
    first_error = exc.errors()[0] if exc.errors() else {}
    
    # Build field path (e.g., "body.request_id" -> "request_id")
    loc = first_error.get("loc", [])
    field = ".".join(str(l) for l in loc if l != "body")
    
    # Get error message
    msg = first_error.get("msg", "Validation failed")
    
    # Construct detail message
    detail = f"{field}: {msg}" if field else msg
    
    # Log validation error
    logger.warning(
        f"Validation error: {detail}",
        extra={"trace_id": trace_id, "field": field, "error_type": first_error.get("type")}
    )
    
    # Create RFC 7807 Problem Details response
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
        headers={"X-Trace-ID": trace_id}
    )


# Initialize processor
processor = DocumentProcessor(runs_root="./runs")


@app.post("/v1/verify", response_model=VerifyResponse)
async def verify_document(
    request: Request,
    file: UploadFile = File(..., description="PDF or image file"),
    fio: str = Form(..., description="Applicant's full name (FIO)"),
):
    """
    Verify a loan deferment document.
    
    Returns:
    - verdict: True if all checks pass, False otherwise
    - errors: List of failed checks (empty if verdict=True)
    - run_id: Unique identifier for this request
    - processing_time_seconds: Total processing duration
    - trace_id: Distributed tracing correlation ID
    """
    start_time = time.time()
    trace_id = getattr(request.state, "trace_id", None)
    
    logger.info(
        f"[NEW REQUEST] FIO={fio}, file={file.filename}",
        extra={"trace_id": trace_id}
    )
    
    # Validate input with new validators
    await validate_upload_file(file)
    verify_req = VerifyRequest(fio=fio)
    
    # Save uploaded file to temp location  
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        # Process document - exceptions handled by middleware
        result = await processor.process_document(
            file_path=tmp_path,
            original_filename=file.filename,
            fio=verify_req.fio,  # Use validated FIO
        )
        
        processing_time = time.time() - start_time
        
        response = VerifyResponse(
            run_id=result["run_id"],
            verdict=result["verdict"],
            errors=result["errors"],
            processing_time_seconds=round(processing_time, 2),
            trace_id=trace_id,
        )
        
        logger.info(
            f"[RESPONSE] run_id={response.run_id}, verdict={response.verdict}, time={response.processing_time_seconds}s",
            extra={"trace_id": trace_id, "run_id": response.run_id}
        )
        return response
    
    finally:
        # Cleanup temp file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "rb-ocr-api",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "service": "[DEV] RB-OCR Document Verification API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.post(
    "/v1/kafka/verify",
    response_model=VerifyResponse,
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
                                "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
                            }
                        },
                        "business_error": {
                            "summary": "Business validation failed",
                            "value": {
                                "run_id": "550e8400-e29b-41d4-a716-446655440001",
                                "verdict": False,
                                "errors": [{"code": "FIO_MISMATCH"}],
                                "processing_time_seconds": 4.5,
                                "trace_id": "b1c2d3e4-f5g6-7890-bcde-fg1234567890"
                            }
                        }
                    }
                }
            }
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
                        "trace_id": "c1d2e3f4-g5h6-7890-cdef-gh1234567890"
                    }
                }
            }
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
                        "trace_id": "d1e2f3g4-h5i6-7890-defg-hi1234567890"
                    }
                }
            }
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
                        "trace_id": "e1f2g3h4-i5j6-7890-efgh-ij1234567890"
                    }
                }
            }
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
                        "trace_id": "f1g2h3i4-j5k6-7890-fghi-jk1234567890"
                    }
                }
            }
        }
    }
)
async def verify_kafka_event(
    request: Request,
    event: KafkaEventRequest,
):
    """
    Process a Kafka event for document verification.
    
    This endpoint:
    1. Receives the Kafka event body with S3 file reference
    2. Validates all input fields (request_id, IIN, S3 path, names)
    3. Stores the event as JSON for audit trail
    4. Builds FIO from name components (last_name + first_name + second_name)
    5. Downloads the document from S3
    6. Runs the verification pipeline
    7. Returns the same response format as /v1/verify
    
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
        extra={"trace_id": trace_id, "request_id": event.request_id}
    )
    
    # Process Kafka event (downloads from S3 and runs pipeline)
    # Exceptions are now handled by the global middleware
    result = await processor.process_kafka_event(
        event_data=event.dict(),
    )
    
    processing_time = time.time() - start_time
    
    response = VerifyResponse(
        run_id=result["run_id"],
        verdict=result["verdict"],
        errors=result["errors"],
        processing_time_seconds=round(processing_time, 2),
        trace_id=trace_id,
    )
    
    logger.info(
        f"[KAFKA RESPONSE] request_id={event.request_id}, "
        f"run_id={response.run_id}, verdict={response.verdict}, "
        f"time={response.processing_time_seconds}s",
        extra={"trace_id": trace_id, "request_id": event.request_id, "run_id": response.run_id}
    )
    return response


# ============================================================================
# The following endpoint uses GET with side effects (document processing).
# This violates REST principles where GET should be idempotent and safe.
# Best Practice: Use POST /v1/kafka/verify instead.
# ============================================================================

@app.get(
    "/v1/kafka/verify-get",
    response_model=VerifyResponse,
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
                                "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
                            }
                        },
                        "business_error": {
                            "summary": "Business validation failed",
                            "value": {
                                "run_id": "550e8400-e29b-41d4-a716-446655440001",
                                "verdict": False,
                                "errors": [{"code": "FIO_MISMATCH"}],
                                "processing_time_seconds": 4.5,
                                "trace_id": "b1c2d3e4-f5g6-7890-bcde-fg1234567890"
                            }
                        }
                    }
                }
            }
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
                        "trace_id": "c1d2e3f4-g5h6-7890-cdef-gh1234567890"
                    }
                }
            }
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
                        "trace_id": "d1e2f3g4-h5i6-7890-defg-hi1234567890"
                    }
                }
            }
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
                        "trace_id": "e1f2g3h4-i5j6-7890-efgh-ij1234567890"
                    }
                }
            }
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
                        "trace_id": "f1g2h3i4-j5k6-7890-fghi-jk1234567890"
                    }
                }
            }
        }
    }
)
async def verify_kafka_event_get(
    request: Request,
    params: KafkaEventQueryParams = Depends(),
):
    """
    Process a Kafka event for document verification using query parameters.
    
    This is a GET equivalent of the POST /v1/kafka/verify endpoint.

    This endpoint:
    1. Receives query parameters (request_id, s3_path, iin, first_name, last_name, second_name)
    2. Validates all input fields (request_id, IIN, S3 path, names)
    3. Stores the event as JSON for audit trail
    4. Builds FIO from name components (last_name + first_name + second_name)
    5. Downloads the document from S3
    6. Runs the verification pipeline
    7. Returns the same response format as /v1/verify
    
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
        extra={"trace_id": trace_id, "request_id": params.request_id}
    )
    
    # Convert query params to dict for processor
    event_data = params.dict()
    
    # Process Kafka event (downloads from S3 and runs pipeline)
    # Exceptions are now handled by the global middleware
    result = await processor.process_kafka_event(
        event_data=event_data,
    )
    
    processing_time = time.time() - start_time
    
    response = VerifyResponse(
        run_id=result["run_id"],
        verdict=result["verdict"],
        errors=result["errors"],
        processing_time_seconds=round(processing_time, 2),
        trace_id=trace_id,
    )
    
    logger.info(
        f"[KAFKA RESPONSE (GET)] request_id={params.request_id}, "
        f"run_id={response.run_id}, verdict={response.verdict}, "
        f"time={response.processing_time_seconds}s",
        extra={"trace_id": trace_id, "request_id": params.request_id, "run_id": response.run_id}
    )
    return response

