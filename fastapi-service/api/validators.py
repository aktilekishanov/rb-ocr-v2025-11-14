import logging
import os
from typing import Final

from fastapi import UploadFile
from pipeline.core.config import MAX_FILE_SIZE_MB
from pipeline.core.const import ALLOWED_CONTENT_TYPES
from pipeline.core.exceptions import PayloadTooLargeError, ValidationError

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES: Final = MAX_FILE_SIZE_MB * 1024 * 1024

MAGIC_BYTES_MAP: Final = {
    b"%PDF": ("pdf", "application/pdf"),
    b"\xff\xd8\xff": ("jpeg", "image/jpeg"),
    b"\x89PNG": ("png", "image/png"),
    b"\x49\x49\x2a\x00": ("tiff", "image/tiff"),
    b"\x4d\x4d\x00\x2a": ("tiff", "image/tiff"),
}


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


def _detect_file_type(file: UploadFile) -> tuple[str, str]:
    file.file.seek(0)
    header = file.file.read(8)
    file.file.seek(0)

    for signature, result in MAGIC_BYTES_MAP.items():
        if header.startswith(signature):
            return result

    raise ValidationError(
        message="Unsupported file type (invalid magic bytes)",
        field="file",
        details={
            "magic_bytes": header.hex(),
            "expected_types": ["pdf", "jpeg", "png", "tiff"],
        },
    )


async def validate_upload_file(file: UploadFile) -> None:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            message=f"Invalid content type: {file.content_type}",
            field="file",
            details={"allowed_types": list(ALLOWED_CONTENT_TYPES)},
        )

    file_size = _get_file_size(file)
    _validate_file_size(file_size)

    detected_type, expected_content_type = _detect_file_type(file)

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
