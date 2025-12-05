"""FastAPI application entry point."""
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from api.schemas import VerifyResponse, KafkaEventRequest
from services.processor import DocumentProcessor
from minio.error import S3Error
import tempfile
import logging
import time
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="[DEV] RB-OCR Document Verification API",
    version="1.0.0",
    description="Validates loan deferment documents",
    docs_url="/docs",
    redoc_url="/redoc",
    root_path="/rb-ocr/api",
)

# Initialize processor
processor = DocumentProcessor(runs_root="./runs")


@app.post("/v1/verify", response_model=VerifyResponse)
async def verify_document(
    file: UploadFile = File(..., description="PDF or image file"),
    fio: str = Form(..., description="Applicant's full name (FIO)"),
):
    """
    Verify a loan deferment document.
    
    Returns:
    - verdict: True if all checks pass, False otherwise
    - errors: List of failed checks (empty if verdict=True)
    - run_id: Unique identifier for this request
    - processing_time_seconds: Total processing duration
    """
    start_time = time.time()
    logger.info(f"[NEW REQUEST] FIO={fio}, file={file.filename}")
    
    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        # Process document
        result = await processor.process_document(
            file_path=tmp_path,
            original_filename=file.filename,
            fio=fio,
        )
        
        processing_time = time.time() - start_time
        
        response = VerifyResponse(
            run_id=result["run_id"],
            verdict=result["verdict"],
            errors=result["errors"],
            processing_time_seconds=round(processing_time, 2),
        )
        
        logger.info(f"[RESPONSE] run_id={response.run_id}, verdict={response.verdict}, time={response.processing_time_seconds}s")
        return response
    
    except Exception as e:
        logger.error(f"[ERROR] {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal processing error: {str(e)}"
        )
    
    finally:
        # Cleanup temp file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "rb-ocr-api",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "service": "[DEV] RB-OCR Document Verification API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.post("/v1/kafka/verify", response_model=VerifyResponse)
async def verify_kafka_event(
    event: KafkaEventRequest,
):
    """
    Process a Kafka event for document verification.
    
    This endpoint:
    1. Receives the Kafka event body with S3 file reference
    2. Stores the event as JSON for audit trail
    3. Builds FIO from name components (last_name + first_name + second_name)
    4. Downloads the document from S3
    5. Runs the verification pipeline
    6. Returns the same response format as /v1/verify
    
    Args:
        event: Kafka event body containing request_id, s3_path, iin, and name fields
        
    Returns:
        VerifyResponse with run_id, verdict, errors, and processing_time_seconds
        
    Raises:
        HTTPException: 500 if S3 download or pipeline processing fails
    """
    start_time = time.time()
    logger.info(
        f"[NEW KAFKA EVENT] request_id={event.request_id}, "
        f"s3_path={event.s3_path}, iin={event.iin}"
    )
    
    try:
        # Process Kafka event (downloads from S3 and runs pipeline)
        result = await processor.process_kafka_event(
            event_data=event.dict(),
        )
        
        processing_time = time.time() - start_time
        
        response = VerifyResponse(
            run_id=result["run_id"],
            verdict=result["verdict"],
            errors=result["errors"],
            processing_time_seconds=round(processing_time, 2),
        )
        
        logger.info(
            f"[KAFKA RESPONSE] request_id={event.request_id}, "
            f"run_id={response.run_id}, verdict={response.verdict}, "
            f"time={response.processing_time_seconds}s"
        )
        return response
    
    except S3Error as e:
        logger.error(f"[S3 ERROR] request_id={event.request_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"S3 download error: {e.code} - {e.message}"
        )
    
    except Exception as e:
        logger.error(
            f"[ERROR] request_id={event.request_id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal processing error: {str(e)}"
        )
