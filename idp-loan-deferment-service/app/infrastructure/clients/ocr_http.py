"""HTTP client adapter for OCR service.

Phase 2: implemented adapter (sync httpx) – not wired into runtime yet.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.ports.ocr_port import OCRPort
from app.domain.pipeline.models import OcrResult, OcrPage

import time
import httpx


class OcrHttpClient(OCRPort):  # pragma: no cover - adapter impl (unused by runtime)
    """OCR HTTP client implementing OCRPort using httpx (sync).

    Assumes endpoints:
    - POST /upload  -> {"job_id": "..."}
    - GET  /result/{job_id} -> {"status": "pending|processing|succeeded|failed", ...}
    When succeeded, JSON should contain pages in either of:
      {"pages": [{"page_number": 1, "text": "..."}, ...]}
      or {"result": {"pages": [...]}}
    """

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
            raise RuntimeError("OCR base_url is not configured")
        return httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout_seconds,
            verify=self._verify_ssl,
            transport=self._transport,
        )

    def upload(self, pdf_path: Path) -> str:
        with self._client() as client:
            with pdf_path.open("rb") as f:
                files = {"file": (pdf_path.name, f, "application/pdf")}
                resp = client.post("/pdf", files=files)
            resp.raise_for_status()
            data = resp.json()
            job_id = data.get("id") or data.get("job_id")
            if not isinstance(job_id, str) or not job_id:
                raise RuntimeError("OCR upload response missing id")
            return job_id

    def wait_result(self, job_id: str, timeout: float, poll_interval: float) -> OcrResult:
        deadline = time.time() + timeout
        with self._client() as client:
            while True:
                resp = client.get(f"/result/{job_id}")
                resp.raise_for_status()
                data = resp.json()
                status = str(data.get("status", "")).lower()
                waiting = {"pending", "processing", "queued", "accepted"}
                success = {"completed", "succeeded", "done"}
                failure = {"failed", "error"}
                if status in waiting or (status == "" and not data.get("result")):
                    if time.time() >= deadline:
                        raise RuntimeError("OCR wait_result timed out")
                    time.sleep(max(poll_interval, 0.01))
                    continue
                if status in success or data.get("success") is True:
                    pages_data = data.get("pages")
                    if pages_data is None and isinstance(data.get("result"), dict):
                        res = data["result"]
                        pages_data = res.get("pages")
                        if pages_data is None and isinstance(res.get("data"), dict):
                            pages_data = res["data"].get("pages")
                    if not isinstance(pages_data, list):
                        raise RuntimeError("OCR result missing pages list")
                    pages = []
                    for idx, p in enumerate(pages_data, start=1):
                        try:
                            pn_raw = p.get("page_number")
                            page_number = int(pn_raw) if pn_raw is not None else int(idx)
                            text = str(p.get("text", ""))
                        except Exception as e:  # pragma: no cover - defensive
                            raise RuntimeError("Invalid page entry in OCR result") from e
                        pages.append(OcrPage(page_number=page_number, text=text))
                    return OcrResult(pages=pages, raw=data)
                if status in failure:
                    err_msg = data.get("error_message") or data.get("error") or "OCR job failed"
                    raise RuntimeError(err_msg)
                # Unknown status: treat as pending
                if time.time() >= deadline:
                    raise RuntimeError("OCR wait_result timed out (unknown status)")
                time.sleep(max(poll_interval, 0.01))
