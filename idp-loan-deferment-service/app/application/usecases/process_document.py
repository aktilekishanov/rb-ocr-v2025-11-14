"""Process document use-case.

Phase 4: application-layer use-case that builds adapters, prepares RunContext,
persists minimal metadata, calls domain pipeline, and returns RunResult.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.application.services.factories import (
    build_storage_adapter,
    build_ocr_client,
    build_llm_client,
)
from app.domain.pipeline.models import RunContext, RunResult
from app.domain.pipeline.orchestrator import run_pipeline
from app.domain.ports.ocr_port import OCRPort
from app.domain.ports.llm_port import LLMPort
from app.domain.pipeline.models import OcrResult, OcrPage, DocTypeResult, ExtractionResult


async def process_document(
    *,
    run_id: str | None,
    input_path: Path,
    extra_meta: dict[str, Any] | None = None,
) -> RunResult:
    """Run the end-to-end domain pipeline for a single document.

    - Saves the input into the runs/ structure
    - Writes a minimal metadata.json
    - Calls the domain pipeline orchestrator
    - Writes a minimal final_result.json
    - Returns the RunResult
    """
    settings = get_settings()
    storage = build_storage_adapter()

    # Choose adapters: real httpx clients if configured, otherwise dev fakes
    if settings.OCR_BASE_URL and settings.LLM_BASE_URL:
        ocr_client: OCRPort = build_ocr_client()
        llm_client: LLMPort = build_llm_client()
    else:
        # Dev-mode fakes to keep runtime self-contained (no external calls)
        class _FakeOCR(OCRPort):  # pragma: no cover - simple dev fallback
            def upload(self, pdf_path: Path) -> str:
                return "job-dev"

            def wait_result(self, job_id: str, timeout: float, poll_interval: float) -> OcrResult:
                # Minimal OCR: produce a single page with placeholder text
                return OcrResult(pages=[OcrPage(page_number=1, text="placeholder text")])

        class _FakeLLM(LLMPort):  # pragma: no cover - simple dev fallback
            def classify_doc_type(self, pages_obj: OcrResult) -> DocTypeResult:
                return DocTypeResult(doc_type="loan_deferment", confidence=None, raw=None)

            def extract_fields(self, pages_obj: OcrResult) -> ExtractionResult:
                # If fio is present in meta, echo it; otherwise empty
                return ExtractionResult(fields={})

        ocr_client = _FakeOCR()
        llm_client = _FakeLLM()

    rid = run_id or str(uuid.uuid4())

    # Persist input and metadata (same layout as existing service)
    saved_input = storage.save_input(rid, input_path)
    storage.write_json(
        rid,
        "meta/metadata.json",
        {
            **(extra_meta or {}),
            "original_path": str(saved_input),
        },
    )

    ctx = RunContext(
        run_id=rid,
        input_path=saved_input,
        work_dir=settings.RUNS_DIR,
        artifacts={},
        meta=extra_meta or {},
    )

    result = await run_pipeline(
        run_id=rid,
        storage=storage,
        ocr_client=ocr_client,
        llm_client=llm_client,
        context=ctx,
    )

    storage.write_json(
        rid,
        "meta/final_result.json",
        {"run_id": result.run_id, "verdict": result.verdict, "errors": list(result.errors)},
    )

    return result
