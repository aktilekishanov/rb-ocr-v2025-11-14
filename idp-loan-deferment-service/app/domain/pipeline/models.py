"""Domain models for the pipeline.

Phase 1: enriched DTOs and result/context models, still unused by runtime code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel


class OcrPage(BaseModel):  # pragma: no cover - Phase 1 DTO
    """Represents text extracted from a single page."""

    page_number: int
    text: str


class OcrResult(BaseModel):  # pragma: no cover - Phase 1 DTO
    """Structured OCR output used by downstream stages."""

    pages: list[OcrPage]
    raw: dict[str, Any] | None = None


class DocTypeResult(BaseModel):  # pragma: no cover - Phase 1 DTO
    """Document type classification result."""

    doc_type: str
    confidence: float | None = None
    raw: dict[str, Any] | None = None


class ExtractionResult(BaseModel):  # pragma: no cover - Phase 1 DTO
    """Field extraction result from LLM or rules."""

    fields: dict[str, Any]
    raw: dict[str, Any] | None = None


class ValidationResult(BaseModel):  # pragma: no cover - Phase 1 DTO
    """Validation outcome for the final decision."""

    is_valid: bool
    errors: list[str]
    warnings: list[str] = []


class RunResult(BaseModel):  # pragma: no cover - Phase 1 model
    """Canonical final result shape for the pipeline."""

    run_id: str
    verdict: bool
    errors: list[str] = []
    checks: dict[str, bool] | None = None
    meta: dict[str, Any] | None = None


class RunContext(BaseModel):  # pragma: no cover - Phase 1 model
    """Context flowing between stages during a pipeline run."""

    run_id: str
    input_path: Path | None = None
    work_dir: Path | None = None
    artifacts: dict[str, Any] = {}
    meta: dict[str, Any] = {}
