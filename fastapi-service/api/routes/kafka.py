"""Kafka event verification endpoints."""

import logging
import time
from typing import Callable, Optional

from api.schemas import (
    KafkaEventQueryParams,
    KafkaEventRequest,
    KafkaResponse,
    VerifyResponse,
)
from core.dependencies import get_db_manager, get_webhook_client
from core.security import sanitize_iin
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pipeline.database.manager import DatabaseManager
from services.mappers import (
    build_external_metadata,
    build_kafka_response,
    build_verify_response,
)
from services.processor import DocumentProcessor
from services.tasks import enqueue_verification_run
from services.webhook_client import WebhookClient

router = APIRouter()
logger = logging.getLogger(__name__)

processor = DocumentProcessor(runs_root="./runs")


async def _process_kafka_event(
    *,
    request: Request,
    background_tasks: BackgroundTasks,
    event_data: dict,
    request_id: Optional[int],
    build_response: Callable,
    external_metadata_builder: Callable,
    db: DatabaseManager,
    webhook: WebhookClient,
    send_webhook: bool,
):
    start_time = time.time()
    trace_id = getattr(request.state, "trace_id", None)

    logger.info(
        "[NEW KAFKA EVENT] request_id=%s s3_path=%s iin=%s",
        request_id,
        event_data.get("s3_path"),
        sanitize_iin(event_data.get("iin")),
        extra={"trace_id": trace_id, "request_id": request_id},
    )

    external_metadata = external_metadata_builder(trace_id)

    result = await processor.process_kafka_event(
        event_data=event_data,
        external_metadata=external_metadata,
    )

    processing_time = time.time() - start_time
    response = build_response(
        result,
        processing_time=processing_time,
        trace_id=trace_id,
        request_id=request_id,
    )

    logger.info(
        "[KAFKA RESPONSE] request_id=%s run_id=%s result=%s time=%.2fs",
        request_id,
        result.get("run_id"),
        getattr(response, "status", getattr(response, "verdict", None)),
        processing_time,
        extra={
            "trace_id": trace_id,
            "request_id": request_id,
            "run_id": result.get("run_id"),
        },
    )

    enqueue_verification_run(
        background_tasks,
        result,
        db,
        webhook if send_webhook else None,
        request_id=request_id if send_webhook else None,
    )

    return response


@router.post(
    "/v1/kafka/verify",
    response_model=VerifyResponse,
    tags=["kafka-integration"],
)
async def verify_kafka_event(
    request: Request,
    background_tasks: BackgroundTasks,
    event: KafkaEventRequest,
    db: DatabaseManager = Depends(get_db_manager),
    webhook: WebhookClient = Depends(get_webhook_client),
):
    return await _process_kafka_event(
        request=request,
        background_tasks=background_tasks,
        event_data=event.dict(),
        request_id=event.request_id,
        build_response=build_verify_response,
        external_metadata_builder=lambda trace_id: build_external_metadata(
            event, trace_id
        ),
        db=db,
        webhook=webhook,
        send_webhook=True,
    )


@router.get(
    "/v1/kafka/verify-get",
    response_model=VerifyResponse,
    tags=["kafka-integration"],
)
async def verify_kafka_event_get(
    request: Request,
    background_tasks: BackgroundTasks,
    params: KafkaEventQueryParams = Depends(),
    db: DatabaseManager = Depends(get_db_manager),
    webhook: WebhookClient = Depends(get_webhook_client),
):
    event = KafkaEventRequest(**params.dict())

    return await _process_kafka_event(
        request=request,
        background_tasks=background_tasks,
        event_data=params.dict(),
        request_id=params.request_id,
        build_response=build_verify_response,
        external_metadata_builder=lambda trace_id: build_external_metadata(
            event, trace_id
        ),
        db=db,
        webhook=webhook,
        send_webhook=True,
    )


@router.post(
    "/v2/kafka/verify",
    response_model=KafkaResponse,
    tags=["kafka-integration"],
)
async def verify_kafka_event_v2(
    request: Request,
    background_tasks: BackgroundTasks,
    event: KafkaEventRequest,
    db: DatabaseManager = Depends(get_db_manager),
    webhook: WebhookClient = Depends(get_webhook_client),
):
    return await _process_kafka_event(
        request=request,
        background_tasks=background_tasks,
        event_data=event.dict(),
        request_id=event.request_id,
        build_response=build_kafka_response,
        external_metadata_builder=lambda trace_id: build_external_metadata(
            event, trace_id
        ),
        db=db,
        webhook=webhook,
        send_webhook=False,
    )


@router.get(
    "/v2/kafka/verify-get",
    response_model=KafkaResponse,
    tags=["kafka-integration"],
)
async def verify_kafka_event_get_v2(
    request: Request,
    background_tasks: BackgroundTasks,
    params: KafkaEventQueryParams = Depends(),
    db: DatabaseManager = Depends(get_db_manager),
    webhook: WebhookClient = Depends(get_webhook_client),
):
    return await _process_kafka_event(
        request=request,
        background_tasks=background_tasks,
        event_data=params.dict(),
        request_id=params.request_id,
        build_response=build_kafka_response,
        external_metadata_builder=lambda trace_id: build_external_metadata(
            params, trace_id
        ),
        db=db,
        webhook=webhook,
        send_webhook=False,
    )
