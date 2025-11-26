from __future__ import annotations

from app.core.config import get_settings
from app.infrastructure.storage.local_disk_adapter import LocalDiskStorageAdapter
from app.infrastructure.clients.ocr_http import OcrHttpClient
from app.infrastructure.clients.completions_http import CompletionsHttpClient
from app.application.llm.adapters.llm_openai_adapter import LlmOpenAIAdapter
from app.domain.ports.llm_port import LLMPort


def build_storage_adapter() -> LocalDiskStorageAdapter:
    s = get_settings()
    return LocalDiskStorageAdapter(base_dir=s.RUNS_DIR)


def build_ocr_client() -> OcrHttpClient:
    s = get_settings()
    return OcrHttpClient(
        base_url=s.OCR_BASE_URL,
        timeout_seconds=s.OCR_TIMEOUT_SECONDS,
        verify_ssl=s.OCR_VERIFY_SSL,
    )


def build_llm_client() -> LLMPort:
    s = get_settings()
    transport = None
    client = CompletionsHttpClient(
        base_url=s.LLM_BASE_URL,
        timeout_seconds=s.LLM_TIMEOUT_SECONDS,
        verify_ssl=s.LLM_VERIFY_SSL,
        transport=transport,
    )
    return LlmOpenAIAdapter(client)
