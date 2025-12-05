"""Pydantic request/response schemas for API endpoints."""
from pydantic import BaseModel, Field
from typing import List


class ErrorDetail(BaseModel):
    """Represents a single validation error."""
    code: str = Field(..., description="Error code (e.g., FIO_MISMATCH)")
    message: str | None = Field(None, description="Human-readable message in Russian")


class VerifyResponse(BaseModel):
    """Response from document verification endpoint."""
    run_id: str = Field(..., description="Unique run identifier")
    verdict: bool = Field(..., description="True if all checks pass")
    errors: List[ErrorDetail] = Field(
        default_factory=list,
        description="List of validation errors"
    )
    processing_time_seconds: float = Field(..., description="Processing duration")

    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "550e8400-e29b-41d4-a716-446655440000",
                "verdict": True,
                "errors": [],
                "processing_time_seconds": 12.4
            }
        }


class KafkaEventRequest(BaseModel):
    """Request schema for Kafka event processing endpoint."""
    request_id: int = Field(..., description="Unique request identifier from Kafka event")
    s3_path: str = Field(..., description="S3 object key/path to the document")
    iin: int = Field(..., description="Individual Identification Number (12 digits)")
    first_name: str = Field(..., description="Applicant's first name")
    last_name: str = Field(..., description="Applicant's last name")
    second_name: str | None = Field(None, description="Applicant's patronymic/middle name (optional)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "request_id": 123123,
                "s3_path": "documents/2024/sample.pdf",
                "iin": 960125000000,
                "first_name": "Иван",
                "last_name": "Иванов",
                "second_name": "Иванович"
            }
        }
