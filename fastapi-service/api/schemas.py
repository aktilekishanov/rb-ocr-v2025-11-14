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
                "run_id": "20251126_140523_abc12",
                "verdict": True,
                "errors": [],
                "processing_time_seconds": 12.4
            }
        }
