"""File upload validation utilities.

This module contains async validation logic for file uploads,
including size checks, content type verification, and magic byte detection.
"""

import logging
import os
from typing import Final

from fastapi import UploadFile
from pipeline.config.constants import ALLOWED_CONTENT_TYPES
from pipeline.config.settings import MAX_FILE_SIZE_MB
from pipeline.errors.exceptions import PayloadTooLargeError, ValidationError
from pipeline.utils.file_detection import detect_file_type_from_bytes

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES: Final = MAX_FILE_SIZE_MB * 1024 * 1024


def _get_file_size(file: UploadFile) -> int:
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    return size


def _validate_file_size(size: int) -> None:
    if size == 0:
        raise ValidationError(
            message="File is empty (0 bytes)",
            field="file",
            details={"file_size": 0},
        )

    if size > MAX_FILE_SIZE_BYTES:
        raise PayloadTooLargeError(
            max_size_mb=MAX_FILE_SIZE_MB,
            actual_size_mb=size / (1024 * 1024),
        )


async def validate_upload_file(file: UploadFile) -> None:
    """Validate uploaded file for content type, size, and magic bytes.

    Args:
        file: FastAPI UploadFile object

    Raises:
        ValidationError: If file fails validation checks
        PayloadTooLargeError: If file exceeds size limit
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            message=f"Invalid content type: {file.content_type}",
            field="file",
            details={"allowed_types": list(ALLOWED_CONTENT_TYPES)},
        )

    file_size = _get_file_size(file)
    _validate_file_size(file_size)

    file.file.seek(0)
    header = file.file.read(8)
    file.file.seek(0)

    result = detect_file_type_from_bytes(header)
    if result is None:
        raise ValidationError(
            message="Unsupported file type (invalid magic bytes)",
            field="file",
            details={
                "magic_bytes": header.hex(),
                "expected_types": ["pdf", "jpeg", "png", "tiff"],
            },
        )

    detected_type, expected_content_type = result

    if file.content_type != expected_content_type:
        logger.warning(
            "Content-Type mismatch: header=%s detected=%s",
            file.content_type,
            expected_content_type,
        )

    logger.info(
        "File validated: type=%s size=%d content_type=%s",
        detected_type,
        file_size,
        file.content_type,
    )
