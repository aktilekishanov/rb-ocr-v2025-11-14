"""Response mapping utilities for API endpoints."""

from api.schemas import KafkaEventRequest, KafkaResponse, VerifyResponse


def build_verify_response(
    result: dict,
    processing_time: float,
    trace_id: str,
    request_id: str | None = None,
) -> VerifyResponse:
    """Map pipeline result to VerifyResponse."""
    return VerifyResponse(
        request_id=request_id,
        run_id=result["run_id"],
        verdict=result["verdict"],
        errors=[e["code"] for e in result["errors"]],
        processing_time_seconds=round(processing_time, 2),
        trace_id=trace_id,
    )


def build_external_metadata(event: KafkaEventRequest, trace_id: str) -> dict:
    """Map Kafka event to internal metadata dictionary."""
    return {
        "trace_id": trace_id,
        "external_request_id": str(event.request_id),
        "external_s3_path": event.s3_path,
        "external_iin": str(event.iin),
        "external_first_name": event.first_name,
        "external_last_name": event.last_name,
        "external_second_name": event.second_name,
    }


def build_kafka_response(
    result: dict,
    request_id: int,
    processing_time: float | None = None,
    trace_id: str | None = None,
) -> KafkaResponse:
    """Map pipeline result to KafkaResponse format.

    Args:
        result: Pipeline result dict
        request_id: Original Kafka event request ID
        processing_time: Processing time (for logging)
        trace_id: Request trace ID (for logging)

    Returns:
        KafkaResponse with status and error codes
    """
    verdict = result.get("verdict", False)
    errors = result.get("errors", [])

    return KafkaResponse(
        request_id=request_id,
        status="success" if verdict else "fail",
        err_codes=[e["code"] for e in errors],
    )
