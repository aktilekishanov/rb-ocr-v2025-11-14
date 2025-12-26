"""FastAPI dependency injection functions.

This module provides dependency injection utilities for FastAPI routes,
enabling clean separation of concerns and improved testability.
"""

from fastapi import HTTPException, Request, status
from pipeline.database.manager import DatabaseManager
from services.webhook_client import WebhookClient


async def get_db_manager(request: Request) -> DatabaseManager:
    """Get database manager from app state.

    Args:
        request: FastAPI request object

    Returns:
        DatabaseManager instance

    Raises:
        HTTPException: 503 if database manager is unavailable
    """
    db_manager = getattr(request.app.state, "db_manager", None)

    if db_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    return db_manager


async def get_webhook_client(request: Request) -> WebhookClient:
    """Get webhook client from app state.

    Args:
        request: FastAPI request object

    Returns:
        WebhookClient instance

    Raises:
        HTTPException: 503 if webhook client is unavailable
    """
    webhook_client = getattr(request.app.state, "webhook_client", None)

    if webhook_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook client unavailable",
        )

    return webhook_client
