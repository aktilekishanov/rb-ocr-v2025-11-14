import time
import logging
from fastapi import APIRouter, Request, BackgroundTasks, Depends
from api.schemas import (
    VerifyResponse,
    KafkaEventRequest,
    KafkaEventQueryParams,
    ProblemDetail,
)
from services.processor import DocumentProcessor
from api.mappers import build_verify_response, build_external_metadata
from services.tasks import enqueue_verification_run

router = APIRouter()
logger = logging.getLogger(__name__)

processor = DocumentProcessor(runs_root="./runs")


@router.post(
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

    external_data = build_external_metadata(event, trace_id)
    result = await processor.process_kafka_event(
        event_data=event.dict(),
        external_metadata=external_data,
    )

    processing_time = time.time() - start_time
    response = build_verify_response(
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

    enqueue_verification_run(background_tasks, result, request_id=event.request_id)
    return response


@router.get(
    "/v1/kafka/verify-get",
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
    external_data = build_external_metadata(event, trace_id)

    result = await processor.process_kafka_event(
        event_data=params.dict(),
        external_metadata=external_data,
    )

    processing_time = time.time() - start_time
    response = build_verify_response(
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

    enqueue_verification_run(background_tasks, result, request_id=params.request_id)
    return response
