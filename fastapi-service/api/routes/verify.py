import logging
import os
import time

from api.mappers import build_verify_response
from api.schemas import ProblemDetail, VerifyRequest, VerifyResponse
from api.validators import validate_upload_file
from core.dependencies import get_db_manager, get_webhook_client
from core.logging_utils import sanitize_fio
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from pipeline.core.database_manager import DatabaseManager
from services.processor import DocumentProcessor
from services.storage import save_upload_to_temp
from services.tasks import enqueue_verification_run
from services.webhook_client import WebhookClient

router = APIRouter()
logger = logging.getLogger(__name__)

processor = DocumentProcessor(runs_root="./runs")


@router.post(
    "/v1/verify",
    response_model=VerifyResponse,
    tags=["manual-verification"],
    responses={422: {"description": "Validation Error", "model": ProblemDetail}},
)
async def verify_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF or image file"),
    fio: str = Form(..., description="Applicant full name (FIO)"),
    db: DatabaseManager = Depends(get_db_manager),
    webhook: WebhookClient = Depends(get_webhook_client),
):
    start_time = time.time()
    trace_id = getattr(request.state, "trace_id", None)

    logger.info(
        "[NEW REQUEST] fio=%s file=%s",
        sanitize_fio(fio),
        file.filename,
        extra={"trace_id": trace_id},
    )

    await validate_upload_file(file)
    verify_req = VerifyRequest(fio=fio)

    tmp_path = await save_upload_to_temp(file)

    try:
        result = await processor.process_document(
            file_path=tmp_path,
            original_filename=file.filename,
            fio=verify_req.fio,
        )

        response = build_verify_response(
            result,
            processing_time=time.time() - start_time,
            trace_id=trace_id,
        )

        logger.info(
            "[RESPONSE] run_id=%s verdict=%s time=%.2fs errors=%s",
            response.run_id,
            response.verdict,
            response.processing_time_seconds,
            response.errors,
            extra={
                "trace_id": trace_id,
                "run_id": response.run_id,
                "errors": response.errors,
            },
        )

        enqueue_verification_run(background_tasks, result, db, webhook)
        return response

    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            logger.warning(
                "Failed to cleanup temp file: %s",
                tmp_path,
                extra={"trace_id": trace_id},
            )
