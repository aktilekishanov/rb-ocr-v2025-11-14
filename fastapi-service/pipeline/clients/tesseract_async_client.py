import asyncio
import json
import mimetypes
import os
from typing import Any

import httpx

from pipeline.core.config import (
    OCR_POLL_INTERVAL_SECONDS,
    OCR_TIMEOUT_SECONDS,
    OCR_CLIENT_TIMEOUT_SECONDS,
    OCR_RAW,
)
from pipeline.processors.image_to_pdf_converter import convert_image_to_pdf
from pipeline.utils.io_utils import write_json


# ============================================================================
# Helper Functions for ask_tesseract
# ============================================================================


def _detect_file_type(pdf_path: str) -> tuple[bool, bool]:
    """Detect if file is PDF or image.
    
    Args:
        pdf_path: Path to file to check
        
    Returns:
        Tuple of (is_pdf, is_image)
    """
    mime_type, _ = mimetypes.guess_type(pdf_path)
    is_pdf = bool(mime_type == "application/pdf" or pdf_path.lower().endswith(".pdf"))
    file_extension = os.path.splitext(pdf_path)[1].lower()
    is_image = bool(
        (mime_type and isinstance(mime_type, str) and mime_type.startswith("image/"))
        or file_extension
        in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".heic", ".heif"}
    )
    return is_pdf, is_image


def _convert_if_needed(pdf_path: str, is_pdf: bool, is_image: bool) -> tuple[str, str | None]:
    """Convert image to PDF if needed.
    
    Args:
        pdf_path: Original file path
        is_pdf: Whether file is already PDF
        is_image: Whether file is an image
        
    Returns:
        Tuple of (work_path, converted_pdf_path)
        - work_path: Path to use for OCR (converted PDF if image, original if PDF)
        - converted_pdf_path: Path to converted PDF if conversion occurred, None otherwise
    """
    if not is_pdf and is_image:
        base_dir = os.path.dirname(pdf_path)
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        desired_path = os.path.join(base_dir, f"{base_name}_converted.pdf")
        converted_pdf = convert_image_to_pdf(pdf_path, output_path=desired_path)
        return converted_pdf, converted_pdf
    return pdf_path, None


def _parse_ocr_result(async_result: dict) -> tuple[bool, str | None, dict]:
    """Parse async OCR result into success, error, raw_obj.
    
    Args:
        async_result: Result dict from ask_tesseract_async
        
    Returns:
        Tuple of (success, error, raw_obj)
    """
    success = bool(async_result.get("success"))
    error: str | None = None
    raw_obj: dict[str, Any] = {}

    get_resp = async_result.get("result")
    if isinstance(get_resp, dict):
        inner = get_resp.get("result")
        if isinstance(inner, dict):
            raw_obj = inner
        else:
            raw_obj = get_resp

    if not success:
        error = async_result.get("error")
        if not error and isinstance(get_resp, dict):
            error = get_resp.get("error_message") or get_resp.get("error")

    return success, error, raw_obj


class TesseractAsyncClient:
    def __init__(
        self,
        base_url: str = "https://ocr.fortebank.com/v2",
        timeout: float = 60.0,
        verify: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._verify = verify
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "TesseractAsyncClient":
        self._client = httpx.AsyncClient(timeout=self._timeout, verify=self._verify)
        return self

    async def __aexit__(self, _exc_type, exc, _tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def upload(self, file_path: str) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError(
                "Client is not started. Use 'async with TesseractAsyncClient()'."
            )
        url = f"{self.base_url}/pdf"
        filename = os.path.basename(file_path)
        with open(file_path, "rb") as file_obj:
            files = {"file": (filename, file_obj, "application/pdf")}
            resp = await self._client.post(url, files=files)
        resp.raise_for_status()
        return resp.json()

    async def get_result(self, file_id: str) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError(
                "Client is not started. Use 'async with TesseractAsyncClient()'."
            )
        url = f"{self.base_url}/result/{file_id}"
        resp = await self._client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def wait_for_result(
        self,
        file_id: str,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError(
                "Client is not started. Use 'async with TesseractAsyncClient()'."
            )
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        last: dict[str, Any] = {}
        while True:
            last = await self.get_result(file_id)
            status = str(last.get("status", "")).lower()
            if (
                status in {"done", "completed", "success", "finished", "ready"}
                or last.get("result") is not None
            ):
                return last
            if status in {"failed", "error"}:
                return last
            if loop.time() >= deadline:
                return last
            await asyncio.sleep(poll_interval)


async def ask_tesseract_async(
    file_path: str,
    *,
    base_url: str = "https://ocr.fortebank.com/v2",
    wait: bool = True,
    poll_interval: float = OCR_POLL_INTERVAL_SECONDS,
    timeout: float = OCR_TIMEOUT_SECONDS,
    client_timeout: float = OCR_CLIENT_TIMEOUT_SECONDS,
    verify: bool = True,
) -> dict[str, Any]:
    async with TesseractAsyncClient(
        base_url=base_url, timeout=client_timeout, verify=verify
    ) as client:
        upload_resp = await client.upload(file_path)
        file_id = upload_resp.get("id")
        result_obj: dict[str, Any] | None = None
        success = False
        error: str | None = None
        if wait and file_id:
            result_obj = await client.wait_for_result(
                file_id, poll_interval=poll_interval, timeout=timeout
            )
            status = str(result_obj.get("status", "")).lower()
            success = bool(
                status in {"done", "completed", "success", "finished", "ready"}
                or result_obj.get("result") is not None
            )
            if not success:
                error = result_obj.get("error") or result_obj.get("message")
        else:
            success = bool(file_id)
        return {
            "success": success,
            "error": error,
            "id": file_id,
            "upload": upload_resp,
            "result": result_obj,
        }


def ask_tesseract(
    pdf_path: str,
    output_dir: str = "output",
    save_json: bool = True,
    *,
    base_url: str = "https://ocr.fortebank.com/v2",
    verify: bool = True,
    poll_interval: float = OCR_POLL_INTERVAL_SECONDS,
    timeout: float = OCR_TIMEOUT_SECONDS,
    client_timeout: float = OCR_CLIENT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Synchronous wrapper for async Tesseract OCR.
    
    Handles file type detection, image-to-PDF conversion if needed,
    async OCR execution, result parsing, and optional JSON saving.
    
    Args:
        pdf_path: Path to PDF or image file
        output_dir: Directory to save OCR results
        save_json: Whether to save raw OCR JSON
        base_url: Tesseract API base URL
        verify: Whether to verify SSL certificates
        poll_interval: Polling interval for OCR completion
        timeout: Overall timeout for OCR operation
        client_timeout: HTTP client timeout
        
    Returns:
        Dict with keys: success, error, raw_path, raw_obj, converted_pdf
    """
    # Detect file type and convert if needed
    is_pdf, is_image = _detect_file_type(pdf_path)
    work_path, converted_pdf = _convert_if_needed(pdf_path, is_pdf, is_image)

    # Run async OCR operation synchronously
    def _run(coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            new_loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(new_loop)
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
                asyncio.set_event_loop(None)
        else:
            return asyncio.run(coro)

    async_result = _run(
        ask_tesseract_async(
            file_path=work_path,
            base_url=base_url,
            wait=True,
            poll_interval=poll_interval,
            timeout=timeout,
            client_timeout=client_timeout,
            verify=verify,
        )
    )

    # Parse OCR result
    success, error, raw_obj = _parse_ocr_result(async_result)
    
    # Save JSON if requested
    raw_path: str | None = None
    if save_json:
        try:
            raw_path = os.path.join(output_dir, OCR_RAW)
            write_json(raw_path, raw_obj if isinstance(raw_obj, dict) else {})
        except Exception:
            raw_path = None

    return {
        "success": success,
        "error": error,
        "raw_path": raw_path,
        "raw_obj": raw_obj if isinstance(raw_obj, dict) else {},
        "converted_pdf": converted_pdf,
    }
