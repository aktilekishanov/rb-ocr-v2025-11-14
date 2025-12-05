"""FastAPI application entry point."""
from fastapi import FastAPI, File, UploadFile, Form, Request
from api.schemas import VerifyResponse, KafkaEventRequest
from api.validators import validate_upload_file, VerifyRequest
from api.middleware.exception_handler import exception_middleware
from services.processor import DocumentProcessor
from pipeline.core.logging_config import configure_structured_logging
from minio.error import S3Error  # Keep this import as it's used in /v1/kafka/verify
import tempfile
import logging
import time
import os

# Configure structured JSON logging for production
configure_structured_logging(level="INFO", json_format=True)
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

# Register global exception middleware
app.middleware("http")(exception_middleware)

# Initialize processor
processor = DocumentProcessor(runs_root="./runs")


@app.post("/v1/verify", response_model=VerifyResponse)
async def verify_document(
    request: Request,
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
    - trace_id: Distributed tracing correlation ID
    """
    start_time = time.time()
    trace_id = getattr(request.state, "trace_id", None)
    
    logger.info(
        f"[NEW REQUEST] FIO={fio}, file={file.filename}",
        extra={"trace_id": trace_id}
    )
    
    # Validate input with new validators
    await validate_upload_file(file)
    verify_req = VerifyRequest(fio=fio)
    
    # Save uploaded file to temp location  
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        # Process document - exceptions handled by middleware
        result = await processor.process_document(
            file_path=tmp_path,
            original_filename=file.filename,
            fio=verify_req.fio,  # Use validated FIO
        )
        
        processing_time = time.time() - start_time
        
        response = VerifyResponse(
            run_id=result["run_id"],
            verdict=result["verdict"],
            errors=result["errors"],
            processing_time_seconds=round(processing_time, 2),
            trace_id=trace_id,
        )
        
        logger.info(
            f"[RESPONSE] run_id={response.run_id}, verdict={response.verdict}, time={response.processing_time_seconds}s",
            extra={"trace_id": trace_id, "run_id": response.run_id}
        )
        return response
    
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
    request: Request,
    event: KafkaEventRequest,
):
    """
    Process a Kafka event for document verification.
    
    This endpoint:
    1. Receives the Kafka event body with S3 file reference
    2. Validates all input fields (request_id, IIN, S3 path, names)
    3. Stores the event as JSON for audit trail
    4. Builds FIO from name components (last_name + first_name + second_name)
    5. Downloads the document from S3
    6. Runs the verification pipeline
    7. Returns the same response format as /v1/verify
    
    Args:
        event: Kafka event body containing request_id, s3_path, iin, and name fields
        
    Returns:
        VerifyResponse with run_id, verdict, errors, processing_time_seconds, and trace_id
    """
    start_time = time.time()
    trace_id = getattr(request.state, "trace_id", None)
    
    logger.info(
        f"[NEW KAFKA EVENT] request_id={event.request_id}, "
        f"s3_path={event.s3_path}, iin={event.iin}",
        extra={"trace_id": trace_id, "request_id": event.request_id}
    )
    
    # Process Kafka event (downloads from S3 and runs pipeline)
    # Exceptions are now handled by the global middleware
    result = await processor.process_kafka_event(
        event_data=event.dict(),
    )
    
    processing_time = time.time() - start_time
    
    response = VerifyResponse(
        run_id=result["run_id"],
        verdict=result["verdict"],
        errors=result["errors"],
        processing_time_seconds=round(processing_time, 2),
        trace_id=trace_id,
    )
    
    logger.info(
        f"[KAFKA RESPONSE] request_id={event.request_id}, "
        f"run_id={response.run_id}, verdict={response.verdict}, "
        f"time={response.processing_time_seconds}s",
        extra={"trace_id": trace_id, "request_id": event.request_id, "run_id": response.run_id}
    )
    return response

