"""Shared Pydantic field validators.

This module contains reusable Pydantic validation functions for common fields
to ensure DRY principle and consistency across all API schemas.
"""

from pipeline.config.settings import IIN_LENGTH, S3_PATH_MAX_LENGTH


def validate_iin_format(iin_value: str) -> str:
    """Validate IIN is exactly 12 digits.

    Args:
        iin_value: The IIN string to validate

    Returns:
        str: The validated IIN

    Raises:
        ValueError: If IIN is not exactly 12 digits or contains non-digits
    """
    if not iin_value.isdigit():
        raise ValueError("IIN must contain only digits")
    if len(iin_value) != IIN_LENGTH:
        raise ValueError(
            f"IIN must be exactly {IIN_LENGTH} digits, got {len(iin_value)}"
        )
    return iin_value


def validate_s3_path_security(s3_path_value: str) -> str:
    """Validate S3 path for security vulnerabilities.

    Security checks:
    - Prevent directory traversal attacks (..)
    - Prevent absolute paths (/)
    - Check max length

    Args:
        s3_path_value: The S3 path to validate

    Returns:
        str: The validated S3 path

    Raises:
        ValueError: If path fails security validation
    """
    if ".." in s3_path_value:
        raise ValueError("S3 path cannot contain '..' (directory traversal)")

    if s3_path_value.startswith("/"):
        raise ValueError("S3 path cannot start with '/' (absolute path)")

    if len(s3_path_value) > S3_PATH_MAX_LENGTH:
        raise ValueError(f"S3 path exceeds maximum length of {S3_PATH_MAX_LENGTH}")

    return s3_path_value
