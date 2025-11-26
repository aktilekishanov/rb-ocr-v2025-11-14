"""Wrapper around pipeline orchestrator for FastAPI."""
from pipeline.orchestrator import run_pipeline
from pathlib import Path
import asyncio
import logging

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Processes documents through the RB-OCR pipeline."""
    
    def __init__(self, runs_root: str = "./runs"):
        self.runs_root = Path(runs_root)
        self.runs_root.mkdir(parents=True, exist_ok=True)
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
