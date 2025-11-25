from __future__ import annotations

from app.domain.pipeline.models import RunContext, OcrResult, ExtractionResult
from app.domain.ports.llm_port import LLMPort
from app.domain.pipeline.errors import LlmError, StageError


def run_extract(context: RunContext, *, llm_client: LLMPort) -> RunContext:
    """Extract fields using LLMPort based on OCR output.

    Attaches ExtractionResult to context.artifacts.
    """
    ocr_result = context.artifacts.get("ocr_result")
    if not isinstance(ocr_result, OcrResult):
        raise StageError("OCR result missing from context for extract stage")
    try:
        ex: ExtractionResult = llm_client.extract_fields(ocr_result)
    except Exception as exc:  # pragma: no cover - exercised via adapter tests
        raise LlmError(f"Field extraction failed: {exc}") from exc

    context.artifacts["extraction_result"] = ex
    return context
