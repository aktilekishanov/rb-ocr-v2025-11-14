"""Domain pipeline orchestrator.

Phase 3: implement orchestration using pure domain stages and ports.
"""

from __future__ import annotations

from .models import RunResult, RunContext
from app.domain.ports.storage_port import StoragePort
from app.domain.ports.ocr_port import OCRPort
from app.domain.ports.llm_port import LLMPort
from app.domain.pipeline.stages.acquire import run_acquire
from app.domain.pipeline.stages.ocr import run_ocr
from app.domain.pipeline.stages.doc_type import run_doc_type
from app.domain.pipeline.stages.extract import run_extract
from app.domain.pipeline.stages.merge import run_merge
from app.domain.pipeline.stages.validate import run_validate


async def run_pipeline(
    *,
    run_id: str,
    storage: StoragePort,
    ocr_client: OCRPort,
    llm_client: LLMPort,
    context: RunContext,
) -> RunResult:  # pragma: no cover - exercised via tests
    """Run the full loan deferment pipeline (pure domain).

    Notes:
    - Does not perform IO directly; relies on ports for OCR/LLM and expects input_path in context.
    - storage is accepted for future use (e.g., artifact persistence) but unused in Phase 3.
    - Keeps timeouts conservative; callers may adjust in later phases.
    """
    # Keep context identity
    ctx = context
    # Acquire
    ctx = run_acquire(ctx)
    # OCR
    ctx = run_ocr(ctx, ocr_client=ocr_client, timeout=60.0, poll_interval=0.25)
    # Doc type
    ctx = run_doc_type(ctx, llm_client=llm_client)
    # Extract
    ctx = run_extract(ctx, llm_client=llm_client)
    # Merge
    ctx = run_merge(ctx)
    # Validate
    ctx, result = run_validate(ctx)
    return result
