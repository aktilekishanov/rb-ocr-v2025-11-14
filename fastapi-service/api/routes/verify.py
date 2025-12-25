import time
import os
import logging
from fastapi import APIRouter, UploadFile, File, Form, Request, BackgroundTasks, Depends
from api.schemas import VerifyResponse, ProblemDetail, VerifyRequest
from api.validators import validate_upload_file
from services.processor import DocumentProcessor
from api.mappers import build_verify_response
from services.storage import save_upload_to_temp
from services.tasks import enqueue_verification_run
from core.dependencies import get_db_manager, get_webhook_client
from pipeline.core.database_manager import DatabaseManager
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
    file: UploadFile = File(..., description="PDF or Image file"),
    fio: str = Form(..., description="Applicant's full name (FIO)"),
    db: DatabaseManager = Depends(get_db_manager),
    webhook: WebhookClient = Depends(get_webhook_client),
):
    """
    Verify a loan deferment document by manually uploading a file.
    """
    start_time = time.time()
    trace_id = getattr(request.state, "trace_id", None)

    logger.info(
        f"[NEW REQUEST] FIO={fio}, file={file.filename}", extra={"trace_id": trace_id}
    )

    # Validate input
    await validate_upload_file(file)
    verify_req = VerifyRequest(fio=fio)

    # Save and process
    tmp_path = await save_upload_to_temp(file)
    try:
        result = await processor.process_document(
            file_path=tmp_path,
            original_filename=file.filename,
            fio=verify_req.fio,
        )

        processing_time = time.time() - start_time
        response = build_verify_response(result, processing_time, trace_id)

        logger.info(
            f"[RESPONSE] run_id={response.run_id}, verdict={response.verdict}, time={response.processing_time_seconds}s, errors={response.errors}",
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
            os.unlink(tmp_path)
        except Exception:
            pass
