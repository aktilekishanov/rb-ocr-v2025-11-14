from api.schemas import HealthResponse
from core.dependencies import get_db_manager
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pipeline.core.database_manager import DatabaseManager

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check(db: DatabaseManager = Depends(get_db_manager)):
    db_health = await db.health_check()
    status_code = 200 if db_health["healthy"] else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if db_health["healthy"] else "unhealthy",
            "service": "rb-ocr-api",
            "version": "1.0.0",
            "database": {
                "status": "connected" if db_health["healthy"] else "disconnected",
                "latency_ms": db_health.get("latency_ms"),
                "error": db_health.get("error"),
            },
        },
    )
