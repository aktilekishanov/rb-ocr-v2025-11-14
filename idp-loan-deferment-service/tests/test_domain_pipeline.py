from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.ports.storage_port import StoragePort
from app.domain.ports.ocr_port import OCRPort
from app.domain.ports.llm_port import LLMPort
from app.domain.pipeline.models import (
    RunContext,
    RunResult,
    OcrResult,
    OcrPage,
    DocTypeResult,
    ExtractionResult,
)
from app.domain.pipeline.orchestrator import run_pipeline


class FakeStorage(StoragePort):  # pragma: no cover
    def __init__(self) -> None:
        self.written: dict[tuple[str, str], dict] = {}

    def save_input(self, run_id: str, src_path: Path) -> Path:
        return src_path

    def write_json(self, run_id: str, rel_path: str, obj: dict) -> Path:
        self.written[(run_id, rel_path)] = obj
        return Path("/dev/null")

    def read_json(self, run_id: str, rel_path: str) -> dict:
        return self.written.get((run_id, rel_path), {})

    def ensure_dirs(self, run_id: str, *rel_dirs: str) -> None:
        return None


class FakeOCR(OCRPort):  # pragma: no cover
    def upload(self, pdf_path: Path) -> str:
        return "job-123"

    def wait_result(self, job_id: str, timeout: float, poll_interval: float) -> OcrResult:
        return OcrResult(pages=[OcrPage(page_number=1, text="hello world")])


class FakeLLM(LLMPort):  # pragma: no cover
    def classify_doc_type(self, pages_obj: OcrResult) -> DocTypeResult:
        return DocTypeResult(doc_type="loan_deferment", confidence=0.9)

    def extract_fields(self, pages_obj: OcrResult) -> ExtractionResult:
        return ExtractionResult(fields={"fio": "John Doe"})


@pytest.mark.asyncio
async def test_run_pipeline_happy_path(tmp_path: Path) -> None:
    storage = FakeStorage()
    ocr_client = FakeOCR()
    llm_client = FakeLLM()

    ctx = RunContext(run_id="run-1", input_path=tmp_path / "doc.pdf")
    result: RunResult = await run_pipeline(
        run_id="run-1",
        storage=storage,
        ocr_client=ocr_client,
        llm_client=llm_client,
        context=ctx,
    )

    assert result.run_id == "run-1"
    assert result.verdict is True
    assert result.errors == []
    assert result.checks is not None and result.checks.get("has_fio") is True
