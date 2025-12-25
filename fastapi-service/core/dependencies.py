"""FastAPI dependency injection functions.

This module provides dependency injection utilities for FastAPI routes,
enabling clean separation of concerns and improved testability.
"""

from fastapi import Request, HTTPException, status
from pipeline.core.database_manager import DatabaseManager
from services.webhook_client import WebhookClient


async def get_db_manager(request: Request) -> DatabaseManager:
    """Dependency to get database manager from app state.

    This dependency retrieves the DatabaseManager instance that was
    initialized during application startup. It enables dependency
    injection in route handlers.

    Usage in routes:
        @router.get("/endpoint")
        async def endpoint(db: DatabaseManager = Depends(get_db_manager)):
            pool = await db.get_pool()
            async with pool.acquire() as conn:
                ...

    Args:
        request: FastAPI request object

    Returns:
        DatabaseManager: The application's database manager

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
    """Dependency to get webhook client from app state.

    This dependency retrieves the WebhookClient instance that was
    initialized during application startup.

    Usage in routes:
        @router.post("/endpoint")
        async def endpoint(webhook: WebhookClient = Depends(get_webhook_client)):
            await webhook.send_result(...)

    Args:
        request: FastAPI request object

    Returns:
        WebhookClient: The application's webhook client

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
