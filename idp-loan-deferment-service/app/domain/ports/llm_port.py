"""LLMPort protocol for LLM-based classification and extraction.

Phase 1: typed DTOs; still a pure interface with no behavior.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.pipeline.models import (
    OcrResult,
    DocTypeResult,
    ExtractionResult,
)


class LLMPort(Protocol):  # pragma: no cover - Phase 0 contract
    """Abstraction over LLM service used by the pipeline."""

    def classify_doc_type(self, pages_obj: OcrResult) -> DocTypeResult: ...

    def extract_fields(self, pages_obj: OcrResult) -> ExtractionResult: ...
