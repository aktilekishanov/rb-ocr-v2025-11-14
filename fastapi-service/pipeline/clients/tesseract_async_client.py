import asyncio
import logging
import os
from typing import Any, Optional

import httpx
from core.settings import ocr_settings
from pipeline.config.settings import (
    OCR_CLIENT_TIMEOUT_SECONDS,
    OCR_RESULT_FILE,
    OCR_TIMEOUT_SECONDS,
)
from pipeline.processors.image_to_pdf_converter import convert_image_to_pdf
from pipeline.utils.file_detection import detect_file_type_from_path
from pipeline.utils.io_utils import write_json

logger = logging.getLogger(__name__)


def parse_ocr_result(resp: dict) -> tuple[bool, Optional[str], dict]:
    """Normalize OCR response."""
    success = bool(resp.get("success"))
    raw = resp.get("result") or {}
    raw_inner = raw.get("result", raw) if isinstance(raw, dict) else {}

    if success:
        return True, None, raw_inner

    error = (
        resp.get("error")
        or raw.get("error_message")
        or raw.get("error")
        or "Unknown OCR error"
    )
    return False, error, raw_inner


class TesseractAsyncClient:
    def __init__(
        self, base_url: Optional[str] = None, timeout: float = 60.0, verify: bool = True
    ):
        self.base_url = base_url or ocr_settings.OCR_BASE_URL
        self.timeout = timeout
        self.verify = verify
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self.timeout, verify=self.verify)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def upload(self, file_path: str) -> dict:
        if not self._client:
            raise RuntimeError("Client not started")
        url = f"{self.base_url}/pdf"
        filename = os.path.basename(file_path)

        with open(file_path, "rb") as f:
            resp = await self._client.post(
                url, files={"file": (filename, f, "application/pdf")}
            )

        resp.raise_for_status()
        return resp.json()

    async def get_result(self, file_id: str) -> dict:
        if not self._client:
            raise RuntimeError("Client not started")
        resp = await self._client.get(f"{self.base_url}/result/{file_id}")
        resp.raise_for_status()
        return resp.json()

    async def wait_for_result(self, file_id: str, timeout: float) -> dict:
        """Poll OCR service until result is ready using exponential backoff."""
        deadline = asyncio.get_event_loop().time() + timeout
        interval, backoff, max_interval = 0.5, 1.5, 5.0
        attempts = 0

        while True:
            attempts += 1
            resp = await self.get_result(file_id)
            status = str(resp.get("status", "")).lower()

            if (
                status in {"done", "completed", "success", "finished", "ready"}
                or resp.get("result") is not None
            ):
                logger.debug("OCR ready after %d checks, file_id=%s", attempts, file_id)
                return resp
            if (
                status in {"failed", "error"}
                or asyncio.get_event_loop().time() >= deadline
            ):
                logger.warning(
                    "OCR failed or timed out after %d checks, file_id=%s, status=%s",
                    attempts,
                    file_id,
                    status,
                )
                return resp

            await asyncio.sleep(interval)
            interval = min(interval * backoff, max_interval)


async def ask_tesseract_async(
    file_path: str,
    *,
    base_url: Optional[str] = None,
    wait: bool = True,
    timeout: float = OCR_TIMEOUT_SECONDS,
    client_timeout: float = OCR_CLIENT_TIMEOUT_SECONDS,
    verify: bool = True,
) -> dict[str, Any]:
    async with TesseractAsyncClient(
        base_url=base_url, timeout=client_timeout, verify=verify
    ) as client:
        upload_resp = await client.upload(file_path)
        file_id = upload_resp.get("id")

        if not wait or not file_id:
            return {
                "success": bool(file_id),
                "error": None if file_id else "Upload failed",
                "id": file_id,
                "upload": upload_resp,
                "result": None,
            }

        result = await client.wait_for_result(file_id, timeout)
        return {
            "success": True,
            "error": None,
            "id": file_id,
            "upload": upload_resp,
            "result": result,
        }


def ask_tesseract(
    pdf_path: str,
    output_dir: str = "output",
    save_json: bool = True,
    *,
    base_url: Optional[str] = None,
    verify: bool = True,
) -> dict[str, Any]:
    result = detect_file_type_from_path(pdf_path)
    if result is None:
        raise ValueError(f"Unsupported file type: {pdf_path}")

    detected_type, mime_type = result

    if detected_type in ("jpeg", "png", "tiff"):
        converted_pdf = f"{os.path.splitext(pdf_path)[0]}_converted.pdf"
        work_path = convert_image_to_pdf(pdf_path, output_path=converted_pdf)
    else:
        work_path = pdf_path
        converted_pdf = None

    async_result = asyncio.run(
        ask_tesseract_async(file_path=work_path, base_url=base_url, verify=verify)
    )

    success, error, raw = parse_ocr_result(async_result)

    raw_path = None
    if save_json:
        os.makedirs(output_dir, exist_ok=True)
        raw_path = os.path.join(output_dir, OCR_RESULT_FILE)
        write_json(raw_path, raw)

    return {
        "success": success,
        "error": error,
        "raw_obj": raw,
        "raw_path": raw_path,
        "converted_pdf": converted_pdf,
    }
