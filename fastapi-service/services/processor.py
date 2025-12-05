"""Wrapper around pipeline orchestrator for FastAPI."""
from pipeline.orchestrator import run_pipeline
from pipeline.utils.io_utils import build_fio, write_json
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
        
        # Initialize S3 client
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
        
        # Run pipeline in executor (it's synchronous)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_pipeline(
                fio=fio,
                source_file_path=file_path,
                original_filename=original_filename,
                content_type=None,
                runs_root=self.runs_root,
            )
        )
        
        logger.info(f"Pipeline complete. run_id={result.get('run_id')}, verdict={result.get('verdict')}")
        
        # Return only API-relevant fields
        return {
            "run_id": result.get("run_id"),
            "verdict": result.get("verdict", False),
            "errors": result.get("errors", []),
        }
    
    async def process_kafka_event(
        self,
        event_data: dict,
    ) -> dict:
        """
        Process a Kafka event containing S3 file reference.
        
        Args:
            event_data: Kafka event body as dict
            
        Returns:
            dict with run_id, verdict, errors
            
        Raises:
            Exception: If S3 download or pipeline processing fails
        """
        request_id = event_data["request_id"]
        s3_path = event_data["s3_path"]
        
        logger.info(f"Processing Kafka event: request_id={request_id}, s3_path={s3_path}")
        
        # 1. Store event body as JSON for audit trail
        event_storage_dir = self.runs_root / "kafka_events"
        event_storage_dir.mkdir(parents=True, exist_ok=True)
        event_file_path = event_storage_dir / f"event_{request_id}_{int(time.time())}.json"
        
        
        write_json(str(event_file_path), event_data)
        logger.info(f"Stored event body: {event_file_path}")
        
        # 2. Build FIO from name components
        fio = build_fio(
            last_name=event_data["last_name"],
            first_name=event_data["first_name"],
            second_name=event_data.get("second_name"),
        )
        logger.info(f"Built FIO: {fio}")
        
        # 3. Download file from S3
        # Extract filename from s3_path or use default
        filename = os.path.basename(s3_path) or f"document_{request_id}.pdf"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
            tmp_path = tmp.name
        
        try:
            # Download from S3
            loop = asyncio.get_event_loop()
            s3_metadata = await loop.run_in_executor(
                None,
                lambda: self.s3_client.download_file(s3_path, tmp_path)
            )
            
            logger.info(f"Downloaded from S3: {s3_path} -> {tmp_path} ({s3_metadata['size']} bytes)")
            
            # 4. Run pipeline
            result = await self.process_document(
                file_path=tmp_path,
                original_filename=filename,
                fio=fio,
            )
            
            logger.info(f"Pipeline complete for Kafka event. run_id={result.get('run_id')}, verdict={result.get('verdict')}")
            
            return result
            
        finally:
            # Cleanup temporary file
            try:
                os.unlink(tmp_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {tmp_path}: {e}")
