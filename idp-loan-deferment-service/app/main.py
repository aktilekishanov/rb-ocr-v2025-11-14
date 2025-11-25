from __future__ import annotations

from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.api.v1.routes_health import router as health_router
from app.api.v1.routes_process import router as process_router
from app.api.v1.routes_jobs import router as jobs_router
from app.observability.metrics import router as metrics_router
from app.observability.metrics import MetricsMiddleware
from app.observability.tracing import init_tracing_if_enabled, instrument_app_if_tracing_enabled
from app.core.config import get_settings
from app.core.logging import RequestIdMiddleware, configure_logging, get_logger

# Initialize settings and logging
settings = get_settings()
configure_logging(settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = get_logger(__name__)
    # Initialize optional tracing and instrument the app if enabled
    try:
        init_tracing_if_enabled(settings)
        instrument_app_if_tracing_enabled(app, settings)
    except Exception:
        pass
    logger.info(
        "service_startup",
        extra={
            "env": settings.ENV,
            "log_level": settings.LOG_LEVEL,
        },
    )
    try:
        yield
    finally:
        logger.info("service_shutdown")


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# Middlewares
app.add_middleware(RequestIdMiddleware)
app.add_middleware(MetricsMiddleware)

# Routers
app.include_router(health_router)
app.include_router(process_router)
app.include_router(jobs_router)
app.include_router(metrics_router)
