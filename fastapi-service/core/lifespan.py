from contextlib import asynccontextmanager
from fastapi import FastAPI
import logging
from pipeline.core.database_manager import create_database_manager_from_env
from services.webhook_client import create_webhook_client_from_env

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown tasks."""

    logger.info("Initializing database connection pool...")
    try:
        db_manager = create_database_manager_from_env()
        await db_manager.connect()
        app.state.db_manager = db_manager
        logger.info("Database pool ready")
    except Exception as e:
        logger.error(f"Database pool initialization failed: {e}", exc_info=True)
        logger.warning("Application will continue without database connectivity")
        app.state.db_manager = None

    logger.info("Initializing webhook client...")
    try:
        webhook_client = create_webhook_client_from_env()
        app.state.webhook_client = webhook_client
        logger.info("Webhook client ready")
    except Exception as e:
        logger.error(f"Webhook client initialization failed: {e}", exc_info=True)
        app.state.webhook_client = None

    yield

    if hasattr(app.state, "db_manager") and app.state.db_manager:
        logger.info("Closing database connection pool...")
        await app.state.db_manager.disconnect()
        logger.info("Database pool closed")
