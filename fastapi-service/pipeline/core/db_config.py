"""PostgreSQL database configuration and connection pooling.

Uses asyncpg for high-performance async PostgreSQL access.
Credentials loaded from environment variables for security.
"""

import asyncpg
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

_missing = []
if not DB_HOST:
    _missing.append("DB_HOST")
if not DB_NAME:
    _missing.append("DB_NAME")
if not DB_USER:
    _missing.append("DB_USER")
if not DB_PASSWORD:
    _missing.append("DB_PASSWORD")

if _missing:
    logger.error(
        f"Missing required database environment variables: {', '.join(_missing)}. "
        "Database functionality will be disabled. "
        "Set these in docker-compose.yml or .env file."
    )
else:
    logger.info(f"Database configuration loaded: {DB_HOST}:{DB_PORT}/{DB_NAME}")

try:
    DB_PORT = int(DB_PORT)
except (TypeError, ValueError):
    logger.error(f"Invalid DB_PORT value: {DB_PORT}. Using default 5432.")
    DB_PORT = 5432

# Connection pool settings (tuned for ~4 req/hour)
DB_POOL_MIN_SIZE = 2
DB_POOL_MAX_SIZE = 10
DB_POOL_TIMEOUT = 10.0  # seconds

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


async def get_db_pool() -> asyncpg.Pool:
    """Get or create the global database connection pool.
    
    Returns:
        asyncpg.Pool: The connection pool instance.
        
    Raises:
        Exception: If pool creation fails.
    """
    global _pool
    
    if _pool is None:
        logger.info(f"Creating database connection pool to {DB_HOST}:{DB_PORT}/{DB_NAME}")
        _pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            min_size=DB_POOL_MIN_SIZE,
            max_size=DB_POOL_MAX_SIZE,
            timeout=DB_POOL_TIMEOUT,
        )
        logger.info(f"Database pool created (min={DB_POOL_MIN_SIZE}, max={DB_POOL_MAX_SIZE})")
    
    return _pool


async def close_db_pool() -> None:
    """Close the database connection pool gracefully."""
    global _pool
    
    if _pool is not None:
        logger.info("Closing database connection pool")
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


async def check_db_health() -> dict[str, Any]:
    """Check database connectivity and return health status.
    
    Returns:
        dict with keys: healthy (bool), error (str|None), latency_ms (float|None)
    """
    import time
    
    try:
        pool = await get_db_pool()
        start = time.time()
        
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        
        latency = (time.time() - start) * 1000
        return {
            "healthy": True,
            "error": None,
            "latency_ms": round(latency, 2)
        }
    except Exception as health_check_err:
        logger.error(f"Database health check failed: {health_check_err}", exc_info=True)
        return {
            "healthy": False,
            "error": str(health_check_err),
            "latency_ms": None
        }
