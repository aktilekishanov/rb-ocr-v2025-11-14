"""Wrapper around pipeline orchestrator for FastAPI."""

from pipeline.orchestrator import run_pipeline
from pipeline.utils.io_utils import build_fio
from pipeline.core.config import s3_config
from services.s3_client import S3Client
from pathlib import Path
import asyncio
import logging
import time
import tempfile
import os

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Processes documents through the RB-OCR pipeline."""

    def __init__(self, runs_root: str = "./runs"):
        self.runs_root = Path(runs_root)
        self.runs_root.mkdir(parents=True, exist_ok=True)

        self.s3_client = S3Client(
            endpoint=s3_config.ENDPOINT,
            access_key=s3_config.ACCESS_KEY,
            secret_key=s3_config.SECRET_KEY,
            bucket=s3_config.BUCKET,
            secure=s3_config.SECURE,
        )

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
            lambda: run_pipeline(
                fio=fio,
                source_file_path=file_path,
                original_filename=original_filename,
                content_type=None,
                runs_root=self.runs_root,
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
        external_metadata: dict | None = None,  # NEW
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
        request_id = event_data["request_id"]
        s3_path = event_data["s3_path"]

        logger.info(
            f"Processing Kafka event: request_id={request_id}, s3_path={s3_path}"
        )

        fio = build_fio(
            last_name=event_data["last_name"],
            first_name=event_data["first_name"],
            second_name=event_data.get("second_name"),
        )
        logger.info(f"Built FIO: {fio}")

        filename = os.path.basename(s3_path) or f"document_{request_id}.pdf"

        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
            tmp_path = tmp.name

        try:
            loop = asyncio.get_event_loop()
            s3_metadata = await loop.run_in_executor(
                None, lambda: self.s3_client.download_file(s3_path, tmp_path)
            )

            logger.info(
                f"Downloaded from S3: {s3_path} -> {tmp_path} ({s3_metadata['size']} bytes)"
            )

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: run_pipeline(
                    fio=fio,
                    source_file_path=tmp_path,
                    original_filename=filename,
                    content_type="application/pdf",
                    runs_root=self.runs_root,
                    external_metadata=external_metadata,
                ),
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
