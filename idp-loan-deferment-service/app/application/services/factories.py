from __future__ import annotations

from app.core.config import get_settings
from app.infrastructure.storage.local_disk_adapter import LocalDiskStorageAdapter
from app.infrastructure.clients.ocr_http import OcrHttpClient
from app.infrastructure.clients.llm_http import LlmHttpClient


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


def build_llm_client() -> LlmHttpClient:
    s = get_settings()
    return LlmHttpClient(
        base_url=s.LLM_BASE_URL,
        timeout_seconds=s.LLM_TIMEOUT_SECONDS,
        verify_ssl=s.LLM_VERIFY_SSL,
    )
