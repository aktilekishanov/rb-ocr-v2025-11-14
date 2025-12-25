from api.schemas import VerifyResponse, KafkaEventRequest, KafkaResponse


def build_verify_response(
    result: dict,
    processing_time: float,
    trace_id: str,
    request_id: str | None = None,
) -> VerifyResponse:
    """
    Map pipeline results to the VerifyResponse DTO.
    Pure transformation, no side effects.
    """
    return VerifyResponse(
        request_id=request_id,
        run_id=result["run_id"],
        verdict=result["verdict"],
        errors=[e["code"] for e in result["errors"]],
        processing_time_seconds=round(processing_time, 2),
        trace_id=trace_id,
    )


def build_external_metadata(event: KafkaEventRequest, trace_id: str) -> dict:
    """
    Map Kafka event data to internal metadata dictionary.
    Pure transformation, no side effects.
    """
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
) -> KafkaResponse:
    """
    Map pipeline results to KafkaResponse format.

    This builds a webhook-compatible response for Kafka endpoints.
    Unlike build_verify_response(), this omits diagnostic fields
    (run_id, trace_id, processing_time) which are only in logs/DB.

    Args:
        result: Pipeline result dict with verdict and errors
        request_id: Original Kafka event request ID

    Returns:
        KafkaResponse with request_id, status, and err_codes
    """
    verdict = result.get("verdict", False)
    errors = result.get("errors", [])

    return KafkaResponse(
        request_id=request_id,
        status="success" if verdict else "fail",
        err_codes=[e["code"] for e in errors],
    )
