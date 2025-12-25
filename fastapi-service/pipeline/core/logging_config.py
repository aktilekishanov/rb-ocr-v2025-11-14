"""Structured logging configuration for production observability.

This module provides JSON-formatted logging for:
- Easy integration with log aggregation systems (ELK, Splunk, CloudWatch)
- Structured querying and filtering
- Trace ID correlation across requests
- Machine-readable log output
"""

import json
import logging
from datetime import datetime


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging.

    Outputs logs as JSON with standard fields plus any extra context
    provided via the 'extra' parameter in logger calls.

    Example:
        >>> logger.info("User login", extra={"user_id": 123, "trace_id": "abc"})
        # Output: {"timestamp": "2025-12-05T17:52:00", "level": "INFO",
        #          "message": "User login", "user_id": 123, "trace_id": "abc"}
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON string with log data
        """
        # Base log data
        log_data = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add process/thread info for debugging
        if record.process:
            log_data["process_id"] = record.process
        if record.thread:
            log_data["thread_id"] = record.thread

        # Add extra fields from logger.info(..., extra={...})
        # Common fields: trace_id, run_id, user_id, request_id, error_code
        for key in [
            "trace_id",
            "run_id",
            "user_id",
            "request_id",
            "error_code",
            "service",
            "duration_ms",
            "http_status",
            "retry_attempt",
        ]:
            if hasattr(record, key):
                log_data[key] = getattr(record, key)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(log_data, ensure_ascii=False, default=str)


def configure_structured_logging(
    level: str = "INFO",
    json_format: bool = True,
) -> None:
    """Configure structured logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON formatter (True) or plain text (False)
    """
    # Clear existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler()

    # Set formatter
    if json_format:
        formatter = StructuredFormatter()
    else:
        # Fallback to standard format for development
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper()))

    # Suppress noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


# For backward compatibility with existing code
def configure_logging(level: str = "INFO") -> None:
    """Legacy function - use configure_structured_logging instead.

    Args:
        level: Logging level
    """
    configure_structured_logging(level=level, json_format=True)
