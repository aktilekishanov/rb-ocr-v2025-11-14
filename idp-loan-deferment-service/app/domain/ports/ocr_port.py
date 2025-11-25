"""OCRPort protocol for OCR service access.

Phase 0: contract only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.domain.pipeline.models import OcrResult


class OCRPort(Protocol):  # pragma: no cover - Phase 0 contract
    """Abstraction over OCR service used by the pipeline."""

    def upload(self, pdf_path: Path) -> str: ...

    def wait_result(self, job_id: str, timeout: float, poll_interval: float) -> OcrResult: ...
