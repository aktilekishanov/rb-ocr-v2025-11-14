"""Domain-level errors for the pipeline.

Phase 1: expanded taxonomy; mapping to HTTP is handled elsewhere.
"""

from __future__ import annotations


class PipelineError(Exception):  # pragma: no cover - Phase 1 taxonomy
    """Base error for domain pipeline failures."""


class InvalidInputError(PipelineError):  # pragma: no cover - Phase 1 taxonomy
    """Raised when the input document is unsupported or malformed."""


class OcrError(PipelineError):  # pragma: no cover - Phase 1 taxonomy
    """Raised when OCR job submission/result retrieval fails or times out."""


class LlmError(PipelineError):  # pragma: no cover - Phase 1 taxonomy
    """Raised when LLM requests fail or return invalid data."""


class StageError(PipelineError):  # pragma: no cover - Phase 1 taxonomy
    """Raised for failures inside a specific pipeline stage (doc-type, extract, merge, validate)."""
