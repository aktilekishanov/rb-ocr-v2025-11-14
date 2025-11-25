from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile

from app.core.logging import get_logger
from app.models.schemas import JobStatusResponse, JobSubmitResponse
from app.services.jobs import get_job_status, submit_job
from app.observability.errors import to_http_error

router = APIRouter(prefix="/v1", tags=["jobs"])


@router.post("/jobs", response_model=JobSubmitResponse)
async def submit(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    fio: str = Form(...),
) -> JobSubmitResponse:
    logger = get_logger(__name__)
    logger.info(
        "job_submit_request_received",
        extra={"uploaded_filename": file.filename, "uploaded_content_type": file.content_type},
    )

    # Validate file type by extension
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    allowed_suffixes = {".pdf", ".jpg", ".jpeg", ".png"}
    if suffix not in allowed_suffixes:
        raise to_http_error("UNSUPPORTED_FILE_TYPE")

    temp_path = None
    try:
        # Stream upload to temp file
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
        run_id = submit_job(background_tasks, file_temp_path=temp_path, fio=fio)
        return JobSubmitResponse(run_id=run_id, status="accepted")
    except Exception as e:
        logger.error("job_submit_failed", extra={"error": str(e)})
        # Best-effort cleanup if we failed before scheduling the background task
        try:
            if temp_path:
                os.unlink(temp_path)
        except Exception:
            pass
        raise to_http_error("JOB_SUBMIT_FAILED")


@router.get("/jobs/{run_id}", response_model=JobStatusResponse)
async def status(run_id: str) -> JobStatusResponse:
    rec = get_job_status(run_id)
    if rec is None:
        # Not tracked in memory (e.g., after restart). For Phase 2 we return 404.
        # A future improvement could read meta/job.json from disk to reconstruct.
        raise to_http_error("JOB_NOT_FOUND")
    return JobStatusResponse(**rec)
