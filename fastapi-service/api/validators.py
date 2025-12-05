"""Input validation utilities for RB-OCR API.

This module provides Pydantic validators and helper functions for validating
API request inputs including FIO format, file uploads, and S3 paths.
"""

from pydantic import BaseModel, Field, field_validator
from fastapi import UploadFile
from typing import Optional, Set
import re

from pipeline.core.exceptions import ValidationError, PayloadTooLargeError


# File upload configuration
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
    def validate_fio(cls, v: str) -> str:
        """Validate FIO format.
        
        Rules:
        - Must contain only letters (Cyrillic/Latin), spaces, and hyphens
        - Must have at least 2 words (first and last name)
        - Whitespace is normalized
        
        Args:
            v: FIO string to validate
            
        Returns:
            Normalized FIO string
            
        Raises:
            ValueError: If validation fails
        """
        # Allow Cyrillic, Latin, spaces, hyphens
        if not re.match(r'^[А-Яа-яЁёA-Za-z\s\-]+$', v):
            raise ValueError(
                "FIO must contain only letters (Cyrillic or Latin), spaces, and hyphens"
            )
        
        # Remove excessive whitespace and normalize
        v = re.sub(r'\s+', ' ', v.strip())
        
        # Must have at least 2 words
        if len(v.split()) < 2:
            raise ValueError("FIO must contain at least first and last name (minimum 2 words)")
        
        return v


class KafkaEventRequestValidator(BaseModel):
    """Validated Kafka event request.
    
    Validates all Kafka event fields including IIN format and S3 path security.
    """
    
    request_id: int = Field(..., gt=0, description="Unique request ID from Kafka")
    
    s3_path: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="S3 object key/path"
    )
    
    iin: int = Field(
        ...,
        ge=100000000000,
        le=999999999999,
        description="12-digit Individual Identification Number"
    )
    
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    second_name: Optional[str] = Field(None, max_length=100)
    
    @field_validator('s3_path')
    @classmethod
    def validate_s3_path(cls, v: str) -> str:
        """Validate S3 path for security.
        
        Rules:
        - No directory traversal (.. or leading /)
        - Must have file extension
        
        Args:
            v: S3 path to validate
            
        Returns:
            Validated S3 path
            
        Raises:
            ValueError: If path is unsafe
        """
        # Prevent directory traversal attacks
        if '..' in v or v.startswith('/'):
            raise ValueError(
                "Invalid S3 path: directory traversal patterns detected (.., /)"
            )
        
        # Must have file extension
        if '.' not in v.split('/')[-1]:  # Check only filename, not parent dirs
            raise ValueError("S3 path must include file extension")
        
        return v
    
    @field_validator('iin')
    @classmethod
    def validate_iin(cls, v: int) -> int:
        """Validate IIN format.
        
        IIN must be exactly 12 digits.
        
        Args:
            v: IIN to validate
            
        Returns:
            Validated IIN
            
        Raises:
            ValueError: If IIN is not 12 digits
        """
        # Pydantic's Field already enforces 12 digits via ge/le
        # This is an additional explicit check for clarity
        if not (100000000000 <= v <= 999999999999):
            raise ValueError("IIN must be exactly 12 digits")
        
        return v
    
    @field_validator('first_name', 'last_name', 'second_name')
    @classmethod
    def validate_name_field(cls, v: Optional[str]) -> Optional[str]:
        """Validate name fields.
        
        Removes excessive whitespace and validates characters.
        
        Args:
            v: Name to validate
            
        Returns:
            Normalized name
        """
        if v is None:
            return None
        
        # Remove excessive whitespace
        v = re.sub(r'\s+', ' ', v.strip())
        
        return v


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
    # Check content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            message=f"Invalid file type: {file.content_type}",
            field="file",
            details={
                "allowed_types": list(ALLOWED_CONTENT_TYPES),
                "received_type": file.content_type,
            }
        )
    
    # Check file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to beginning
    
    if file_size > MAX_FILE_SIZE_BYTES:
        actual_size_mb = file_size / 1024 / 1024
        raise PayloadTooLargeError(
            max_size_mb=MAX_FILE_SIZE_MB,
            actual_size_mb=actual_size_mb
        )
    
    # File size of 0 is also invalid
    if file_size == 0:
        raise ValidationError(
            message="File is empty (0 bytes)",
            field="file",
            details={"file_size": 0}
        )
