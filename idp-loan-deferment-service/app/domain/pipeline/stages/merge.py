from __future__ import annotations

from app.domain.pipeline.models import RunContext, OcrResult, DocTypeResult, ExtractionResult
from app.domain.pipeline.errors import StageError


def run_merge(context: RunContext) -> RunContext:
    """Merge OCR, doc-type, and extraction artifacts into a single dict.

    Stores the merged dict under context.artifacts["merged"].
    """
    ocr = context.artifacts.get("ocr_result")
    dt = context.artifacts.get("doc_type_result")
    ex = context.artifacts.get("extraction_result")

    if not isinstance(ocr, OcrResult) or not isinstance(dt, DocTypeResult) or not isinstance(ex, ExtractionResult):
        raise StageError("Missing required artifacts for merge stage")

    fields = dict(ex.fields)
    # If fio is present in meta but missing from extracted fields, inject it.
    fio = context.meta.get("fio")
    if fio is not None and "fio" not in fields:
        fields["fio"] = fio

    merged = {
        "doc_type": dt.doc_type,
        "doc_type_confidence": dt.confidence,
        "fields": fields,
    }
    context.artifacts["merged"] = merged
    return context
