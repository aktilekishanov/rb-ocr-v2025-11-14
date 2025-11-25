from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.core.logging import get_logger

router = APIRouter(tags=["health"]) 


@router.get("/health")
async def health(request: Request):
    """Liveness check: process is up."""
    settings = get_settings()
    logger = get_logger(__name__)
    logger.info("health", extra={"path": str(request.url.path)})
    return {"status": "ok", "service": settings.APP_NAME}


@router.get("/ready")
async def ready(request: Request):
    """Readiness check: ready to accept traffic.
    Phase 0: same as /health; extended checks can be added later.
    """
    settings = get_settings()
    logger = get_logger(__name__)
    logger.info("ready", extra={"path": str(request.url.path)})
    return {"status": "ok", "service": settings.APP_NAME}
