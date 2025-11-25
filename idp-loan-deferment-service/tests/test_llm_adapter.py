from __future__ import annotations

import httpx
import pytest

from app.infrastructure.clients.llm_http import LlmHttpClient
from app.domain.pipeline.models import OcrResult, OcrPage, DocTypeResult, ExtractionResult


def test_llm_adapter_classify_and_extract_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # type: ignore[override]
        if request.method == "POST" and request.url.path == "/doc-type":
            return httpx.Response(200, json={"doc_type": "loan_deferment", "confidence": 0.92})
        if request.method == "POST" and request.url.path == "/extract":
            return httpx.Response(200, json={"fields": {"fio": "Jane Doe", "amount": 123}})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    client = LlmHttpClient(base_url="https://example.com", timeout_seconds=5, verify_ssl=True, transport=transport)

    ocr = OcrResult(pages=[OcrPage(page_number=1, text="hello"), OcrPage(page_number=2, text="world")])
    dt = client.classify_doc_type(ocr)
    assert isinstance(dt, DocTypeResult)
    assert dt.doc_type == "loan_deferment"
    assert dt.confidence is not None

    ex = client.extract_fields(ocr)
    assert isinstance(ex, ExtractionResult)
    assert "fio" in ex.fields
    assert ex.fields["amount"] == 123


def test_llm_adapter_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # type: ignore[override]
        if request.method == "POST" and request.url.path == "/doc-type":
            # Missing doc_type
            return httpx.Response(200, json={"confidence": 0.5})
        if request.method == "POST" and request.url.path == "/extract":
            # fields is not a dict
            return httpx.Response(200, json={"fields": [1, 2, 3]})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    client = LlmHttpClient(base_url="https://example.com", timeout_seconds=5, verify_ssl=True, transport=transport)

    ocr = OcrResult(pages=[OcrPage(page_number=1, text="hello")])

    with pytest.raises(RuntimeError):
        client.classify_doc_type(ocr)

    with pytest.raises(RuntimeError):
        client.extract_fields(ocr)
