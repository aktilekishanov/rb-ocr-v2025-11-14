from __future__ import annotations

import httpx
import pytest

from app.infrastructure.clients.completions_http import CompletionsHttpClient
from app.application.llm.adapters.llm_openai_adapter import LlmOpenAIAdapter
from app.domain.pipeline.models import OcrResult, OcrPage, DocTypeResult, ExtractionResult


def _json_line(obj: dict) -> str:
    import json
    return json.dumps(obj)


def test_llm_adapter_classify_and_extract_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # type: ignore[override]
        if request.method == "POST" and request.url.path == "/openai/v1/completions/v2":
            # Return two JSON lines; last contains the assistant content
            line1 = _json_line({"echo": True})
            line2 = _json_line({
                "choices": [
                    {"message": {"content": "{\"doc_type\":\"loan_deferment\",\"confidence\":0.92}"}}
                ]
            })
            return httpx.Response(200, text=f"{line1}\n{line2}", headers={"Content-Type": "text/plain"})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    client = CompletionsHttpClient(
        base_url="https://example.com/openai/v1/completions/v2",
        timeout_seconds=5,
        verify_ssl=True,
        transport=transport,
    )
    adapter = LlmOpenAIAdapter(client)

    ocr = OcrResult(pages=[OcrPage(page_number=1, text="hello"), OcrPage(page_number=2, text="world")])
    dt = adapter.classify_doc_type(ocr)
    assert isinstance(dt, DocTypeResult)
    assert dt.doc_type == "loan_deferment"
    assert dt.confidence is not None

    def handler2(request: httpx.Request) -> httpx.Response:  # type: ignore[override]
        if request.method == "POST" and request.url.path == "/openai/v1/completions/v2":
            line2 = _json_line({
                "choices": [
                    {"message": {"content": "{\"fields\": {\"fio\": \"Jane Doe\", \"amount\": 123}}"}}
                ]
            })
            return httpx.Response(200, text=line2, headers={"Content-Type": "text/plain"})
        return httpx.Response(404, json={"detail": "not found"})

    adapter._client = CompletionsHttpClient(
        base_url="https://example.com/openai/v1/completions/v2",
        timeout_seconds=5,
        verify_ssl=True,
        transport=httpx.MockTransport(handler2),
    )
    ex = adapter.extract_fields(ocr)
    assert isinstance(ex, ExtractionResult)
    assert ex.fields.get("fio") == "Jane Doe"
    assert ex.fields.get("amount") == 123


def test_llm_adapter_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # type: ignore[override]
        if request.method == "POST" and request.url.path == "/openai/v1/completions/v2":
            line2 = _json_line({
                "choices": [
                    {"message": {"content": "not a json"}}
                ]
            })
            return httpx.Response(200, text=line2, headers={"Content-Type": "text/plain"})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    client = CompletionsHttpClient(
        base_url="https://example.com/openai/v1/completions/v2",
        timeout_seconds=5,
        verify_ssl=True,
        transport=transport,
    )
    adapter = LlmOpenAIAdapter(client)

    ocr = OcrResult(pages=[OcrPage(page_number=1, text="hello")])

    with pytest.raises(RuntimeError):
        adapter.classify_doc_type(ocr)
