from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile, HTTPException

from app.core.logging import get_logger
from app.models.schemas import ProcessResponse
from app.application.services.pipeline_runner import run_sync_pipeline_app
from app.observability.errors import to_http_error

router = APIRouter(prefix="/v1", tags=["process"])


@router.post("/process", response_model=ProcessResponse)
async def process_document(
    request: Request,
    file: UploadFile = File(...),
    fio: str = Form(...),
):
    logger = get_logger(__name__)
    logger.info(
        "process_request_received",
        extra={"uploaded_filename": file.filename, "uploaded_content_type": file.content_type},
    )

    # Basic file-type validation by extension to avoid obviously invalid inputs
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    allowed_suffixes = {".pdf", ".jpg", ".jpeg", ".png"}
    if suffix not in allowed_suffixes:
        raise to_http_error("UNSUPPORTED_FILE_TYPE")

    # Save uploaded file to a temporary location
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            temp_path = tmp.name
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)
    except Exception as e:
        raise to_http_error("UPLOAD_READ_FAILED", message=f"Failed to read uploaded file: {e}")
    finally:
        try:
            await file.close()
        except Exception:
            pass

    try:
        result = await run_sync_pipeline_app(run_id=None, input_path=Path(temp_path), meta={"fio": fio})
        return ProcessResponse(**result)
    except Exception as e:
        logger.error("process_failed", extra={"error": str(e)})
        raise to_http_error("INTERNAL_PROCESSING_ERROR")
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass
