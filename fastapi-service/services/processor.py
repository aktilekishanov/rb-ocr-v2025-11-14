"""Wrapper around pipeline orchestrator for FastAPI."""

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from core.settings import s3_settings
from fastapi import UploadFile
from pipeline.errors.exceptions import ExternalServiceError
from pipeline.orchestrator import PipelineRunner
from pipeline.utils.io_utils import build_fio
from services.s3_client import S3Client

logger = logging.getLogger(__name__)


async def _save_upload_to_temp(file: UploadFile) -> str:
    """Save uploaded file to temporary location.

    Returns:
        Absolute path to temporary file
    """
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=f"_{file.filename}"
    ) as temp_file:
        content = await file.read()
        temp_file.write(content)
        return temp_file.name


def _extract_event_fields(event_data: dict) -> tuple[str, str, str]:
    """Extract request_id, s3_path, and filename from event data."""
    from pathlib import Path

    request_id = event_data["request_id"]
    s3_path = event_data["s3_path"]
    filename = Path(s3_path).name or f"document_{request_id}.pdf"
    return request_id, s3_path, filename


def _build_fio_from_event(event_data: dict) -> str:
    """Build full name from first, last, and optional second name."""
    return build_fio(
        last_name=event_data["last_name"],
        first_name=event_data["first_name"],
        second_name=event_data.get("second_name"),
    )


async def _download_from_s3_async(
    s3_client: S3Client, s3_path: str, tmp_path: str
) -> dict:
    """Download file from S3 to temp path asynchronously."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: s3_client.download_file(s3_path, tmp_path)
    )


async def _run_pipeline_async(
    fio: str,
    tmp_path: str,
    filename: str,
    runs_root: Path,
    external_metadata: dict | None,
) -> dict:
    """Execute pipeline in thread pool executor."""
    loop = asyncio.get_event_loop()
    runner = PipelineRunner(runs_root)
    return await loop.run_in_executor(
        None,
        lambda: runner.run(
            fio=fio,
            source_file_path=tmp_path,
            original_filename=filename,
            external_metadata=external_metadata,
        ),
    )


class DocumentProcessor:
    """Processes documents through the RB-OCR pipeline."""

    def __init__(self, runs_root: str = "./runs"):
        self.runs_root = Path(runs_root)
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.runner = PipelineRunner(self.runs_root)

        try:
            self.s3_client = S3Client(
                endpoint=s3_settings.S3_ENDPOINT,
                access_key=s3_settings.S3_ACCESS_KEY,
                secret_key=s3_settings.S3_SECRET_KEY.get_secret_value(),
                bucket=s3_settings.S3_BUCKET,
                secure=s3_settings.S3_SECURE,
            )
        except Exception as e:
            logger.error(
                f"Failed to initialize S3Client: {e}. Kafka/S3 features will be disabled."
            )
            self.s3_client = None

        logger.info(f"DocumentProcessor initialized. runs_root={self.runs_root}")

    async def process_document(
        self,
        file_path: str,
        original_filename: str,
        fio: str,
    ) -> dict:
        """
        Process a document through the pipeline.

        Args:
            file_path: Temporary file path
            original_filename: Original uploaded filename
            fio: Applicant's full name

        Returns:
            dict with run_id, verdict, errors
        """
        logger.info(f"Processing: {original_filename} for FIO: {fio}")

        self.runs_root.mkdir(parents=True, exist_ok=True)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.runner.run(
                fio=fio,
                source_file_path=file_path,
                original_filename=original_filename,
            ),
        )

        logger.info(
            f"Pipeline complete. run_id={result.get('run_id')}, verdict={result.get('verdict')}"
        )

        return {
            "run_id": result.get("run_id"),
            "verdict": result.get("verdict", False),
            "errors": result.get("errors", []),
            "final_result_path": result.get("final_result_path"),
        }

    async def process_kafka_event(
        self,
        event_data: dict,
        external_metadata: dict | None = None,
    ) -> dict:
        """
        Process a Kafka event containing S3 file reference.

        Args:
            event_data: Kafka event body as dict
            external_metadata: Optional dict with trace_id and external metadata

        Returns:
            dict with run_id, verdict, errors

        Raises:
            Exception: If S3 download or pipeline processing fails
        """
        request_id, s3_path, filename = _extract_event_fields(event_data)
        fio = _build_fio_from_event(event_data)

        logger.info(
            f"Processing Kafka event: request_id={request_id}, s3_path={s3_path}"
        )
        logger.info(f"Built FIO: {fio}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
            tmp_path = tmp.name

        try:
            if not self.s3_client:
                raise ExternalServiceError(
                    service_name="S3",
                    error_type="unavailable",
                    details={
                        "reason": "Missing S3 configuration (endpoint/credentials)"
                    },
                )

            s3_metadata = await _download_from_s3_async(
                self.s3_client, s3_path, tmp_path
            )
            logger.info(
                f"Downloaded from S3: {s3_path} -> {tmp_path} ({s3_metadata['size']} bytes)"
            )

            result = await _run_pipeline_async(
                fio, tmp_path, filename, self.runs_root, external_metadata
            )
            logger.info(
                f"Pipeline completed: run_id={result.get('run_id')}, verdict={result.get('verdict')}"
            )

            return {
                "run_id": result.get("run_id"),
                "verdict": result.get("verdict", False),
                "errors": result.get("errors", []),
                "final_result_path": result.get("final_result_path"),
            }
        finally:
            try:
                os.remove(tmp_path)
                logger.debug(f"Removed temp file: {tmp_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temp file {tmp_path}: {e}")
