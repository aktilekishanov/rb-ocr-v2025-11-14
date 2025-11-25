from __future__ import annotations

from pathlib import Path

from app.domain.pipeline.models import (
    RunResult,
    RunContext,
    OcrPage,
    OcrResult,
    DocTypeResult,
    ExtractionResult,
    ValidationResult,
)
from app.domain.ports.storage_port import StoragePort
from app.domain.ports.ocr_port import OCRPort
from app.domain.ports.llm_port import LLMPort


class FakeStorage(StoragePort):  # pragma: no cover
    def save_input(self, run_id: str, src_path: Path) -> Path:
        return Path("/tmp")

    def write_json(self, run_id: str, rel_path: str, obj: dict) -> Path:
        return Path("/tmp")

    def read_json(self, run_id: str, rel_path: str) -> dict:
        return {}

    def ensure_dirs(self, run_id: str, *rel_dirs: str) -> None:
        return None


class FakeOCR(OCRPort):  # pragma: no cover
    def upload(self, pdf_path: Path) -> str:
        return "job-123"

    def wait_result(self, job_id: str, timeout: float, poll_interval: float) -> OcrResult:
        return OcrResult(pages=[OcrPage(page_number=1, text="hello")])


class FakeLLM(LLMPort):  # pragma: no cover
    def classify_doc_type(self, pages_obj: OcrResult) -> DocTypeResult:
        return DocTypeResult(doc_type="loan_deferment", confidence=0.9)

    def extract_fields(self, pages_obj: OcrResult) -> ExtractionResult:
        return ExtractionResult(fields={"fio": "John Doe"})


def test_models_instantiation() -> None:
    rr = RunResult(run_id="r1", verdict=True, errors=[])
    assert rr.run_id == "r1"
    assert rr.verdict is True

    rc = RunContext(run_id="r1", input_path=None)
    assert rc.run_id == "r1"

    ocr = OcrResult(pages=[OcrPage(page_number=1, text="t")])
    assert len(ocr.pages) == 1

    dt = DocTypeResult(doc_type="x")
    assert dt.doc_type == "x"

    ex = ExtractionResult(fields={})
    assert isinstance(ex.fields, dict)

    val = ValidationResult(is_valid=True, errors=[])
    assert val.is_valid is True


def test_ports_protocols() -> None:
    storage: StoragePort = FakeStorage()
    ocr_client: OCRPort = FakeOCR()
    llm_client: LLMPort = FakeLLM()

    assert isinstance(storage.save_input("r1", Path("/tmp/test.pdf")), Path)
    job_id = ocr_client.upload(Path("/tmp/test.pdf"))
    assert isinstance(job_id, str)
    ocr_res = ocr_client.wait_result(job_id, timeout=1.0, poll_interval=0.1)
    assert isinstance(ocr_res, OcrResult)

    dt_res = llm_client.classify_doc_type(ocr_res)
    assert isinstance(dt_res, DocTypeResult)
    ex_res = llm_client.extract_fields(ocr_res)
    assert isinstance(ex_res, ExtractionResult)
