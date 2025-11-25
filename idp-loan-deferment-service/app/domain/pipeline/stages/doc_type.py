from __future__ import annotations

from app.domain.pipeline.models import RunContext, OcrResult, DocTypeResult
from app.domain.ports.llm_port import LLMPort
from app.domain.pipeline.errors import LlmError, StageError


def run_doc_type(context: RunContext, *, llm_client: LLMPort) -> RunContext:
    """Classify document type using LLMPort based on OCR output.

    Attaches DocTypeResult to context.artifacts and sets context.meta["doc_type"].
    """
    ocr_result = context.artifacts.get("ocr_result")
    if not isinstance(ocr_result, OcrResult):
        raise StageError("OCR result missing from context for doc_type stage")
    try:
        dt: DocTypeResult = llm_client.classify_doc_type(ocr_result)
    except Exception as exc:  # pragma: no cover - exercised via adapter tests
        raise LlmError(f"Doc-type classification failed: {exc}") from exc

    context.artifacts["doc_type_result"] = dt
    context.meta.setdefault("doc_type", dt.doc_type)
    return context
