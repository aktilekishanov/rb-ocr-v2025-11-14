from __future__ import annotations

from app.domain.ports.llm_port import LLMPort
from app.domain.pipeline.models import OcrResult, DocTypeResult, ExtractionResult
from app.application.llm.prompts import build_doc_type_prompt, build_extract_prompt
from app.application.llm.parsers import parse_doc_type, parse_fields
from app.infrastructure.clients.completions_http import CompletionsHttpClient


class LlmOpenAIAdapter(LLMPort):
    def __init__(
        self,
        client: CompletionsHttpClient,
        *,
        model: str = "gpt-4o",
        temperature: float = 0.1,
        max_tokens: int = 1500,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def classify_doc_type(self, pages_obj: OcrResult) -> DocTypeResult:
        text = "\n\n".join(p.text for p in pages_obj.pages)
        prompt = build_doc_type_prompt(text)
        data = self._client.complete(
            prompt,
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        content = self._client.extract_message_content(data)
        doc_type, confidence, raw = parse_doc_type(content)
        return DocTypeResult(doc_type=doc_type, confidence=confidence, raw=raw)

    def extract_fields(self, pages_obj: OcrResult) -> ExtractionResult:
        text = "\n\n".join(p.text for p in pages_obj.pages)
        prompt = build_extract_prompt(text)
        data = self._client.complete(
            prompt,
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        content = self._client.extract_message_content(data)
        fields, raw = parse_fields(content)
        return ExtractionResult(fields=fields, raw=raw)
