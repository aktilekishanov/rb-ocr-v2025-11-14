from contextlib import asynccontextmanager
from fastapi import FastAPI
import logging
from pipeline.core.db_config import get_db_pool, close_db_pool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown tasks."""

    logger.info("Initializing database connection pool...")
    try:
        pool = await get_db_pool()
        logger.info("Database pool ready")
    except Exception as e:
        logger.error(f"Database pool initialization failed: {e}", exc_info=True)
        logger.warning("Application will continue without database connectivity")

    yield

    logger.info("Closing database connection pool...")
    await close_db_pool()
    logger.info("Database pool closed")
