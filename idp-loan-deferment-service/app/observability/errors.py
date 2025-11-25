from __future__ import annotations

from typing import Any

from fastapi import HTTPException


ERROR_REGISTRY: dict[str, dict[str, Any]] = {
    "UNSUPPORTED_FILE_TYPE": {
        "status": 400,
        "message": "Unsupported file type. Allowed: pdf, jpg, jpeg, png",
    },
    "UPLOAD_READ_FAILED": {
        "status": 400,
        "message": "Failed to read uploaded file",
    },
    "INTERNAL_PROCESSING_ERROR": {
        "status": 500,
        "message": "Internal processing error",
    },
    "JOB_SUBMIT_FAILED": {
        "status": 500,
        "message": "Internal job submission error",
    },
    "JOB_NOT_FOUND": {
        "status": 404,
        "message": "Job not found",
    },
}


def to_http_error(code: str, *, message: str | None = None, status: int | None = None) -> HTTPException:
    meta = ERROR_REGISTRY.get(code, {"status": 500, "message": code})
    status_code = int(status or meta.get("status", 500))
    detail_msg = message or str(meta.get("message", code))
    return HTTPException(status_code=status_code, detail={"code": code, "message": detail_msg})
