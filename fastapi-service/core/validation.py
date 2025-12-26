"""Application startup validation checks.

Validates critical settings and configuration before application starts.
Follows SRP: Settings classes define data, this module validates behavior.
"""

import logging
import re

logger = logging.getLogger(__name__)


def validate_all_settings() -> None:
    """Validate all critical settings at application startup.

    This ensures the application fails fast if environment is misconfigured,
    rather than crashing on first request.

    Raises:
        RuntimeError: If any critical setting is missing or invalid
    """
    from core.settings import (
        db_settings,
        llm_settings,
        ocr_settings,
        s3_settings,
        webhook_settings,
    )

    critical_checks = [
        (db_settings.DB_HOST, "DB_HOST", "Database connection"),
        (db_settings.DB_PORT, "DB_PORT", "Database connection"),
        (db_settings.DB_NAME, "DB_NAME", "Database connection"),
        (db_settings.DB_USER, "DB_USER", "Database connection"),
        (
            db_settings.DB_PASSWORD.get_secret_value(),
            "DB_PASSWORD",
            "Database connection",
        ),
        (s3_settings.S3_ENDPOINT, "S3_ENDPOINT", "S3/MinIO storage"),
        (s3_settings.S3_BUCKET, "S3_BUCKET", "S3/MinIO storage"),
        (s3_settings.S3_ACCESS_KEY, "S3_ACCESS_KEY", "S3/MinIO storage"),
        (
            s3_settings.S3_SECRET_KEY.get_secret_value(),
            "S3_SECRET_KEY",
            "S3/MinIO storage",
        ),
        (webhook_settings.WEBHOOK_URL, "WEBHOOK_URL", "Webhook integration"),
        (ocr_settings.OCR_BASE_URL, "OCR_BASE_URL", "OCR service"),
        (llm_settings.LLM_ENDPOINT_URL, "LLM_ENDPOINT_URL", "LLM service"),
    ]

    missing = []
    for value, name, purpose in critical_checks:
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(f"  - {name} (required for {purpose})")

    if missing:
        error_msg = (
            "❌ Missing critical environment variables:\n"
            + "\n".join(missing)
            + "\n\nPlease check your .env file or environment configuration."
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    url_pattern = re.compile(r"^https?://.+")
    url_checks = [
        (webhook_settings.WEBHOOK_URL, "WEBHOOK_URL"),
        (ocr_settings.OCR_BASE_URL, "OCR_BASE_URL"),
        (llm_settings.LLM_ENDPOINT_URL, "LLM_ENDPOINT_URL"),
    ]

    invalid_urls = []
    for url, name in url_checks:
        if url and not url_pattern.match(url):
            invalid_urls.append(
                f"  - {name}={url} (must start with http:// or https://)"
            )

    if invalid_urls:
        error_msg = "❌ Invalid URL formats:\n" + "\n".join(invalid_urls)
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    if not (1 <= db_settings.DB_PORT <= 65535):
        raise RuntimeError(f"DB_PORT must be 1-65535, got {db_settings.DB_PORT}")

    if db_settings.DB_POOL_MIN_SIZE > db_settings.DB_POOL_MAX_SIZE:
        raise RuntimeError(
            f"DB_POOL_MIN_SIZE ({db_settings.DB_POOL_MIN_SIZE}) "
            f"cannot exceed DB_POOL_MAX_SIZE ({db_settings.DB_POOL_MAX_SIZE})"
        )

    logger.info("✅ All critical settings validated successfully")
    logger.info(
        f"  - Database: {db_settings.DB_HOST}:{db_settings.DB_PORT}/{db_settings.DB_NAME}"
    )
    logger.info(f"  - S3: {s3_settings.S3_ENDPOINT}/{s3_settings.S3_BUCKET}")
    logger.info(f"  - OCR: {ocr_settings.OCR_BASE_URL}")
    logger.info(f"  - LLM: {llm_settings.LLM_ENDPOINT_URL}")
    logger.info(f"  - Webhook: {webhook_settings.WEBHOOK_URL}")
