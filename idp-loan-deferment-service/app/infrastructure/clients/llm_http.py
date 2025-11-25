"""HTTP client adapter for LLM service.

Phase 2: implemented adapter (sync httpx) – not wired into runtime yet.
"""

from __future__ import annotations

from app.domain.ports.llm_port import LLMPort
from app.domain.pipeline.models import OcrResult, DocTypeResult, ExtractionResult
import httpx


class LlmHttpClient(LLMPort):  # pragma: no cover - adapter impl (unused by runtime)
    """LLM HTTP client implementing LLMPort using httpx (sync)."""

    def __init__(
        self,
        base_url: str | None,
        timeout_seconds: int,
        verify_ssl: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._verify_ssl = verify_ssl
        self._transport = transport

    def _client(self) -> httpx.Client:
        if not self._base_url:
            raise RuntimeError("LLM base_url is not configured")
        return httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout_seconds,
            verify=self._verify_ssl,
            transport=self._transport,
        )

    def classify_doc_type(self, pages_obj: OcrResult) -> DocTypeResult:
        payload = {"pages": [p.text for p in pages_obj.pages]}
        with self._client() as client:
            resp = client.post("/doc-type", json=payload)
            resp.raise_for_status()
            data = resp.json()
            doc_type = data.get("doc_type")
            if not isinstance(doc_type, str) or not doc_type:
                raise RuntimeError("LLM classify_doc_type missing doc_type")
            confidence = data.get("confidence")
            try:
                conf_val = float(confidence) if confidence is not None else None
            except Exception:
                conf_val = None
            return DocTypeResult(doc_type=doc_type, confidence=conf_val, raw=data)

    def extract_fields(self, pages_obj: OcrResult) -> ExtractionResult:
        payload = {"pages": [p.text for p in pages_obj.pages]}
        with self._client() as client:
            resp = client.post("/extract", json=payload)
            resp.raise_for_status()
            data = resp.json()
            fields = data.get("fields", {})
            if not isinstance(fields, dict):
                raise RuntimeError("LLM extract_fields missing fields dict")
            return ExtractionResult(fields=fields, raw=data)
