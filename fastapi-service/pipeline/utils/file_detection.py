"""
Centralized file type detection using magic bytes.

This module provides the ONLY file type detection logic in the entire
application. All other modules MUST import from here.

Magic bytes reference:
- PDF:  %PDF (0x25504446)
- JPEG: 0xFFD8FF
- PNG:  0x89504E47 (89 P N G)
- TIFF: 0x49492A00 (little-endian) or 0x4D4D002A (big-endian)
"""

from typing import Final, Literal

FileType = Literal["pdf", "jpeg", "png", "tiff"]
MimeType = Literal["application/pdf", "image/jpeg", "image/png", "image/tiff"]

MAGIC_BYTES_MAP: Final[dict[bytes, tuple[FileType, MimeType]]] = {
    b"%PDF": ("pdf", "application/pdf"),
    b"\xff\xd8\xff": ("jpeg", "image/jpeg"),
    b"\x89PNG": ("png", "image/png"),
    b"\x49\x49\x2a\x00": ("tiff", "image/tiff"),
    b"\x4d\x4d\x00\x2a": ("tiff", "image/tiff"),
}


def detect_file_type_from_bytes(
    header: bytes,
) -> tuple[FileType, MimeType] | None:
    """
    Detect file type from magic bytes header.

    Args:
        header: First 8+ bytes of file

    Returns:
        Tuple of (file_type, mime_type) or None if unrecognized

    Example:
        >>> header = b'%PDF-1.4'
        >>> detect_file_type_from_bytes(header)
        ('pdf', 'application/pdf')
    """
    for signature, result in MAGIC_BYTES_MAP.items():
        if header.startswith(signature):
            return result
    return None


def detect_file_type_from_path(
    file_path: str,
) -> tuple[FileType, MimeType] | None:
    """
    Detect file type by reading magic bytes from disk.

    Args:
        file_path: Path to file

    Returns:
        Tuple of (file_type, mime_type) or None if unrecognized or read error

    Example:
        >>> detect_file_type_from_path('/tmp/doc.pdf')
        ('pdf', 'application/pdf')
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(8)
        return detect_file_type_from_bytes(header)
    except (OSError, IOError):
        return None
