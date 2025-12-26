"""Retry decorator for database operations.

Provides exponential backoff retry logic for transient failures.
"""

import asyncio
import logging
from functools import wraps
from typing import Callable, TypeVar

from pipeline.config.settings import BACKOFF_MULTIPLIER, INITIAL_BACKOFF, MAX_RETRIES

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_on_db_error(
    max_retries: int = MAX_RETRIES,
    initial_backoff: float = INITIAL_BACKOFF,
    backoff_multiplier: float = BACKOFF_MULTIPLIER,
) -> Callable:
    """Decorator to retry async database operations on failure.

    Uses exponential backoff: 1s, 2s, 4s, ...

    Args:
        max_retries: Maximum number of retry attempts
        initial_backoff: Initial delay in seconds
        backoff_multiplier: Multiplier for each retry

    Returns:
        Decorated function that retries on exception

    Example:
        @retry_on_db_error(max_retries=3)
        async def insert_data(...):
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except Exception as e:
                    if attempt < max_retries:
                        backoff = initial_backoff * (
                            backoff_multiplier ** (attempt - 1)
                        )
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt}/{max_retries}), "
                            f"retrying in {backoff}s: {e}"
                        )
                        await asyncio.sleep(backoff)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries} attempts: {e}",
                            exc_info=True,
                        )
                        raise

            raise RuntimeError(f"{func.__name__} exhausted retries")

        return wrapper

    return decorator
