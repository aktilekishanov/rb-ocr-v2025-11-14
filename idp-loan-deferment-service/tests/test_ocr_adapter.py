from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.infrastructure.clients.ocr_http import OcrHttpClient
from app.domain.pipeline.models import OcrResult


def test_ocr_adapter_upload_and_wait_success(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # type: ignore[override]
        if request.method == "POST" and request.url.path == "/upload":
            return httpx.Response(200, json={"job_id": "job-123"})
        if request.method == "GET" and request.url.path == "/result/job-123":
            payload = {
                "status": "succeeded",
                "pages": [
                    {"page_number": 1, "text": "hello"},
                    {"page_number": 2, "text": "world"},
                ],
            }
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    client = OcrHttpClient(base_url="https://example.com", timeout_seconds=5, verify_ssl=True, transport=transport)

    # Create a fake PDF
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%")

    job_id = client.upload(pdf)
    assert job_id == "job-123"

    result = client.wait_result(job_id, timeout=1.0, poll_interval=0.01)
    assert isinstance(result, OcrResult)
    assert len(result.pages) == 2
    assert result.pages[0].page_number == 1
    assert result.pages[0].text == "hello"


def test_ocr_adapter_wait_failed_raises(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # type: ignore[override]
        if request.method == "POST" and request.url.path == "/upload":
            return httpx.Response(200, json={"job_id": "job-err"})
        if request.method == "GET" and request.url.path == "/result/job-err":
            return httpx.Response(200, json={"status": "failed", "error": "bad ocr"})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    client = OcrHttpClient(base_url="https://example.com", timeout_seconds=5, verify_ssl=True, transport=transport)

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%")

    job_id = client.upload(pdf)
    assert job_id == "job-err"

    with pytest.raises(RuntimeError):
        client.wait_result(job_id, timeout=0.1, poll_interval=0.01)
