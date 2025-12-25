"""Database connection pool manager with proper lifecycle management.

This module provides a DatabaseManager class that encapsulates the asyncpg
connection pool with explicit lifecycle control, enabling dependency injection
and improved testability.
"""

import logging
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connection pool lifecycle.

    This class encapsulates the connection pool and provides a clean
    interface for acquiring connections. It supports explicit initialization
    and cleanup, making it easy to mock for testing.

    Example:
        db = DatabaseManager(host="localhost", port=5432, ...)
        await db.connect()
        pool = await db.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(...)
        await db.disconnect()
    """

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        min_size: int = 2,
        max_size: int = 10,
        timeout: float = 10.0,
    ):
        """Initialize database configuration (doesn't connect yet).

        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            min_size: Minimum pool size
            max_size: Maximum pool size
            timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.min_size = min_size
        self.max_size = max_size
        self.timeout = timeout

        self._pool: Optional[asyncpg.Pool] = None
        self._closed = False

    async def connect(self) -> None:
        """Create the connection pool.

        Raises:
            Exception: If pool creation fails
        """
        if self._pool is not None:
            logger.warning("Database pool already exists")
            return

        logger.info(
            f"Creating database pool: {self.host}:{self.port}/{self.database} "
            f"(min={self.min_size}, max={self.max_size})"
        )

        self._pool = await asyncpg.create_pool(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            min_size=self.min_size,
            max_size=self.max_size,
            timeout=self.timeout,
        )

        logger.info("Database pool created successfully")

    async def disconnect(self) -> None:
        """Close the connection pool gracefully."""
        if self._pool is None:
            return

        logger.info("Closing database connection pool")
        await self._pool.close()
        self._pool = None
        self._closed = True
        logger.info("Database pool closed")

    async def get_pool(self) -> asyncpg.Pool:
        """Get the connection pool.

        Returns:
            asyncpg.Pool: The connection pool

        Raises:
            RuntimeError: If pool not initialized or already closed
        """
        if self._closed:
            raise RuntimeError("Database manager has been closed")

        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        return self._pool

    async def health_check(self) -> dict:
        """Check database connectivity.

        Returns:
            dict: Health status with 'healthy', 'error', and 'latency_ms' keys
        """
        import time

        try:
            pool = await self.get_pool()
            start = time.time()

            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")

            latency = (time.time() - start) * 1000
            return {"healthy": True, "error": None, "latency_ms": round(latency, 2)}
        except Exception as e:
            logger.error(f"Database health check failed: {e}", exc_info=True)
            return {"healthy": False, "error": str(e), "latency_ms": None}


def create_database_manager_from_env() -> DatabaseManager:
    """Factory function to create DatabaseManager from environment variables.

    Required environment variables:
        DB_HOST: Database host
        DB_PORT: Database port (default: 5432)
        DB_NAME: Database name
        DB_USER: Database user
        DB_PASSWORD: Database password

    Optional:
        DB_POOL_MIN_SIZE: Minimum pool size (default: 2)
        DB_POOL_MAX_SIZE: Maximum pool size (default: 10)
        DB_POOL_TIMEOUT: Connection timeout (default: 10.0)

    Returns:
        DatabaseManager: Configured database manager instance

    Raises:
        ValueError: If required environment variables are missing
    """
    import os

    host = os.getenv("DB_HOST")
    port = int(os.getenv("DB_PORT", "5432"))
    database = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if not all([host, database, user, password]):
        raise ValueError(
            "Missing required database environment variables: "
            "DB_HOST, DB_NAME, DB_USER, DB_PASSWORD"
        )

    return DatabaseManager(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        min_size=int(os.getenv("DB_POOL_MIN_SIZE", "2")),
        max_size=int(os.getenv("DB_POOL_MAX_SIZE", "10")),
        timeout=float(os.getenv("DB_POOL_TIMEOUT", "10.0")),
    )
