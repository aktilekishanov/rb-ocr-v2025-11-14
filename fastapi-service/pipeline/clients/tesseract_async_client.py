import asyncio
import mimetypes
import os
from typing import Any

import httpx

from pipeline.core.config import (
    OCR_POLL_INTERVAL_SECONDS,
    OCR_TIMEOUT_SECONDS,
    OCR_CLIENT_TIMEOUT_SECONDS,
    OCR_RESULT_FILE,
)
from pipeline.processors.image_to_pdf_converter import convert_image_to_pdf
from pipeline.utils.io_utils import write_json


# ------------------------------------------------------------
# Parsing utilities
# ------------------------------------------------------------


def _parse_ocr_result(resp: dict) -> tuple[bool, str | None, dict]:
    """Normalize OCR response."""
    success = bool(resp.get("success"))
    raw = resp.get("result") or {}
    raw_inner = raw.get("result", raw) if isinstance(raw, dict) else {}

    if success:
        return True, None, raw_inner

    # Try get error
    err = (
        resp.get("error")
        or raw.get("error_message")
        or raw.get("error")
        or "Unknown OCR error"
    )

    return False, err, raw_inner


# ------------------------------------------------------------
# File utilities
# ------------------------------------------------------------


def _detect_file_type(path: str) -> tuple[bool, bool]:
    mime, _ = mimetypes.guess_type(path)
    ext = os.path.splitext(path)[1].lower()

    is_pdf = ext == ".pdf" or mime == "application/pdf"
    is_image = (mime and mime.startswith("image/")) or ext in {
        ".png",
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".bmp",
        ".webp",
        ".heic",
        ".heif",
    }
    return is_pdf, is_image


def _convert_if_needed(
    path: str, is_pdf: bool, is_image: bool
) -> tuple[str, str | None]:
    """Convert image to PDF if needed."""
    if is_image and not is_pdf:
        base = os.path.splitext(path)[0]
        out = f"{base}_converted.pdf"
        pdf_path = convert_image_to_pdf(path, output_path=out)
        return pdf_path, pdf_path
    return path, None


# ------------------------------------------------------------
# OCR Client
# ------------------------------------------------------------


class TesseractAsyncClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 60.0,
        verify: bool = True,
    ) -> None:
        self.base_url = base_url or os.getenv("OCR_BASE_URL")
        self.timeout = timeout
        self.verify = verify
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "TesseractAsyncClient":
        self._client = httpx.AsyncClient(timeout=self.timeout, verify=self.verify)
        return self

    async def __aexit__(self, *_):
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

    async def wait_for_result(
        self,
        file_id: str,
        poll_interval: float,
        timeout: float,
    ) -> dict:
        """Poll OCR service until result is ready."""
        deadline = asyncio.get_event_loop().time() + timeout

        while True:
            resp = await self.get_result(file_id)
            status = str(resp.get("status", "")).lower()

            if status in {"done", "completed", "success", "finished", "ready"}:
                return resp
            if resp.get("result") is not None:
                return resp
            if status in {"failed", "error"}:
                return resp
            if asyncio.get_event_loop().time() >= deadline:
                return resp

            await asyncio.sleep(poll_interval)


# ------------------------------------------------------------
# High-level async API
# ------------------------------------------------------------


async def ask_tesseract_async(
    file_path: str,
    *,
    base_url: str | None = None,
    wait: bool = True,
    poll_interval: float = OCR_POLL_INTERVAL_SECONDS,
    timeout: float = OCR_TIMEOUT_SECONDS,
    client_timeout: float = OCR_CLIENT_TIMEOUT_SECONDS,
    verify: bool = True,
) -> dict[str, Any]:
    async with TesseractAsyncClient(
        base_url=base_url,
        timeout=client_timeout,
        verify=verify,
    ) as client:
        upload = await client.upload(file_path)
        file_id = upload.get("id")

        if not wait or not file_id:
            return {
                "success": bool(file_id),
                "error": None if file_id else "Upload failed",
                "id": file_id,
                "upload": upload,
                "result": None,
            }

        result = await client.wait_for_result(
            file_id,
            poll_interval=poll_interval,
            timeout=timeout,
        )

        return {
            "success": True,
            "error": None,
            "id": file_id,
            "upload": upload,
            "result": result,
        }


# ------------------------------------------------------------
# Synchronous wrapper
# ------------------------------------------------------------


def ask_tesseract(
    pdf_path: str,
    output_dir: str = "output",
    save_json: bool = True,
    *,
    base_url: str | None = None,
    verify: bool = True,
    poll_interval: float = OCR_POLL_INTERVAL_SECONDS,
    timeout: float = OCR_TIMEOUT_SECONDS,
    client_timeout: float = OCR_CLIENT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    # Detect + convert
    is_pdf, is_image = _detect_file_type(pdf_path)
    work_path, converted_pdf = _convert_if_needed(pdf_path, is_pdf, is_image)

    # Run async OCR
    async_result = asyncio.run(
        ask_tesseract_async(
            file_path=work_path,
            base_url=base_url,
            verify=verify,
            poll_interval=poll_interval,
            timeout=timeout,
            client_timeout=client_timeout,
        )
    )

    # Normalize
    success, error, raw = _parse_ocr_result(async_result)

    raw_path = None
    if save_json:
        raw_path = os.path.join(output_dir, OCR_RESULT_FILE)
        write_json(raw_path, raw)

    return {
        "success": success,
        "error": error,
        "raw_obj": raw,
        "raw_path": raw_path,
        "converted_pdf": converted_pdf,
    }
