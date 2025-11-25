from __future__ import annotations

from app.domain.pipeline.models import RunContext, OcrResult
from app.domain.ports.ocr_port import OCRPort
from app.domain.pipeline.errors import OcrError


def run_ocr(context: RunContext, *, ocr_client: OCRPort, timeout: float, poll_interval: float) -> RunContext:
    """Run OCR via OCRPort and attach OcrResult to context artifacts.

    Raises OcrError on failures.
    """
    if context.input_path is None:
        raise OcrError("input_path is not set in RunContext for OCR stage")
    try:
        job_id = ocr_client.upload(context.input_path)
        ocr_result: OcrResult = ocr_client.wait_result(job_id, timeout=timeout, poll_interval=poll_interval)
    except Exception as exc:  # pragma: no cover - exercised via adapter tests
        raise OcrError(f"OCR failed: {exc}") from exc

    context.artifacts["ocr_result"] = ocr_result
    return context
