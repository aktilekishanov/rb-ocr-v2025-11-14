"""Input validation utilities for RB-OCR API.

This module provides Pydantic validators and helper functions for validating
API request inputs including FIO format, file uploads, and S3 paths.
"""

from pydantic import BaseModel, Field, field_validator
from fastapi import UploadFile
from typing import Optional, Set
import re

from pipeline.core.exceptions import ValidationError, PayloadTooLargeError


ALLOWED_CONTENT_TYPES: Set[str] = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/jpg",
}

MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


class VerifyRequest(BaseModel):
    """Validated request for document verification.
    
    Validates that FIO contains only valid characters and has at least 2 words.
    """
    
    fio: str = Field(
        ...,
        min_length=3,
        max_length=200,
        description="Full name of applicant (Cyrillic or Latin)"
    )
    
    @field_validator('fio')
    @classmethod
    def validate_fio(cls, fio_value: str) -> str:
        """Validate FIO format.
        
        Rules:
        - Must contain only letters (Cyrillic/Latin), spaces, and hyphens
        - Must have at least 2 words (first and last name)
        - Whitespace is normalized
        
        Args:
            fio_value: FIO string to validate
            
        Returns:
            Normalized FIO string
            
        Raises:
            ValueError: If validation fails
        """
        if not re.match(r'^[А-Яа-яЁёA-Za-z\s\-]+$', fio_value):
            raise ValueError(
                "FIO must contain only letters (Cyrillic or Latin), spaces, and hyphens"
            )
        
        fio_value = re.sub(r'\s+', ' ', fio_value.strip())
        
        if len(fio_value.split()) < 2:
            raise ValueError("FIO must contain at least first and last name (minimum 2 words)")
        
        return fio_value




async def validate_upload_file(file: UploadFile) -> None:
    """Validate uploaded file.
    
    Checks:
    - Content type is allowed (PDF, JPEG, PNG, TIFF)
    - File size is within limits (max 50MB)
    
    Args:
        file: Uploaded file to validate
        
    Raises:
        ValidationError: If content type is invalid
        PayloadTooLargeError: If file exceeds size limit
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            message=f"Invalid file type: {file.content_type}",
            field="file",
            details={
                "allowed_types": list(ALLOWED_CONTENT_TYPES),
                "received_type": file.content_type,
            }
        )
    
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > MAX_FILE_SIZE_BYTES:
        actual_size_mb = file_size / 1024 / 1024
        raise PayloadTooLargeError(
            max_size_mb=MAX_FILE_SIZE_MB,
            actual_size_mb=actual_size_mb
        )
    
    if file_size == 0:
        raise ValidationError(
            message="File is empty (0 bytes)",
            field="file",
            details={"file_size": 0}
        )
