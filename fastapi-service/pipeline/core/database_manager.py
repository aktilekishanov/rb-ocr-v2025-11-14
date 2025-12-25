"""
DatabaseManager with lifecycle, health check, and env-based config.
"""

import logging
import os
import time
from typing import Optional, Dict

import asyncpg

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Asyncpg connection pool manager with explicit lifecycle."""

    def __init__(
        self,
        host: str,
        database: str,
        user: str,
        password: str,
        port: int = 5432,
        min_size: int = 5,
        max_size: int = 30,
        timeout: float = 10.0,
        command_timeout: float = 10.0,
    ):
        self._config = dict(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            command_timeout=command_timeout,
        )
        self._pool: Optional[asyncpg.Pool] = None
        self._closed = False

    async def connect(self) -> None:
        """Initialize the connection pool."""
        if self._pool:
            logger.warning("Database pool already initialized")
            return
        self._pool = await asyncpg.create_pool(**self._config)
        logger.info("Database pool created")

    async def disconnect(self) -> None:
        """Close the connection pool."""
        if not self._pool:
            return
        await self._pool.close()
        self._pool = None
        self._closed = True
        logger.info("Database pool closed")

    async def get_pool(self) -> asyncpg.Pool:
        """Return the connection pool."""
        if self._closed:
            raise RuntimeError("DatabaseManager is closed")
        if not self._pool:
            raise RuntimeError("Database pool not initialized. Call connect() first")
        return self._pool

    async def health_check(self) -> Dict[str, Optional[float]]:
        """Check database connectivity and measure latency."""
        try:
            pool = await self.get_pool()
            start = time.time()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            latency_ms = round((time.time() - start) * 1000, 2)
            return {"healthy": True, "error": None, "latency_ms": latency_ms}
        except Exception as e:
            logger.error("Database health check failed", exc_info=True)
            return {"healthy": False, "error": str(e), "latency_ms": None}

    # Context manager support
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()


def create_database_manager_from_env() -> DatabaseManager:
    """Create DatabaseManager from environment variables (fail-fast)."""
    required_vars = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    config = {}
    missing = []

    for var in required_vars:
        val = os.getenv(var)
        if not val:
            missing.append(var)
        else:
            config[var.lower()[3:]] = val

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    def parse_int(env_var: str) -> Optional[int]:
        val = os.getenv(env_var)
        if val is None:
            return None
        try:
            return int(val)
        except ValueError:
            raise ValueError(f"Invalid integer value for {env_var}: {val}")

    def parse_float(env_var: str) -> Optional[float]:
        val = os.getenv(env_var)
        if val is None:
            return None
        try:
            return float(val)
        except ValueError:
            raise ValueError(f"Invalid float value for {env_var}: {val}")

    optional_vars = {
        "DB_PORT": parse_int,
        "DB_POOL_MIN_SIZE": parse_int,
        "DB_POOL_MAX_SIZE": parse_int,
        "DB_POOL_TIMEOUT": parse_float,
        "DB_COMMAND_TIMEOUT": parse_float,
    }

    for env_var, parser in optional_vars.items():
        if val := parser(env_var):
            key = env_var.lower()[3:]
            config[key] = val

    config.setdefault("port", 5432)
    return DatabaseManager(**config)
