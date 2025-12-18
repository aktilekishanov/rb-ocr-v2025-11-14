from fastapi import UploadFile
import os

from pipeline.core.exceptions import ValidationError, PayloadTooLargeError
from pipeline.core.config import MAX_FILE_SIZE_MB
from pipeline.core.const import ALLOWED_CONTENT_TYPES


def _validate_content_type(file: UploadFile) -> None:
    """Validate file content type."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            message=f"Invalid file type: {file.content_type}",
            field="file",
            details={
                "allowed_types": list(ALLOWED_CONTENT_TYPES),
                "received_type": file.content_type,
            },
        )


def _get_file_size(file: UploadFile) -> int:
    """Get file size and reset file position."""
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0, os.SEEK_SET)
    return file_size


def _validate_file_size(file_size: int) -> None:
    """Validate file size is within limits and not empty."""
    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        actual_size_mb = file_size / (1024 * 1024)
        raise PayloadTooLargeError(
            max_size_mb=MAX_FILE_SIZE_MB, actual_size_mb=actual_size_mb
        )

    if file_size == 0:
        raise ValidationError(
            message="File is empty (0 bytes)", field="file", details={"file_size": 0}
        )


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
    _validate_content_type(file)
    file_size = _get_file_size(file)
    _validate_file_size(file_size)
