from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Type, Tuple


def retry(
    fn: Callable[..., Any],
    *args: Any,
    retries: int = 2,
    backoff: float = 0.2,
    max_backoff: float = 1.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    **kwargs: Any,
) -> Any:
    """Simple sync retry with exponential backoff.

    Parameters mirror the Phase 3 plan. Backoff doubles each attempt up to max_backoff.
    """
    attempt = 0
    delay = backoff
    while True:
        try:
            return fn(*args, **kwargs)
        except exceptions as e:
            if attempt >= retries:
                raise
            time.sleep(delay)
            delay = min(delay * 2, max_backoff)
            attempt += 1


async def async_retry(
    fn: Callable[..., Awaitable[Any]],
    *args: Any,
    retries: int = 2,
    backoff: float = 0.2,
    max_backoff: float = 1.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    **kwargs: Any,
) -> Any:
    """Simple async retry with exponential backoff.

    Parameters mirror the Phase 3 plan. Backoff doubles each attempt up to max_backoff.
    """
    attempt = 0
    delay = backoff
    while True:
        try:
            return await fn(*args, **kwargs)
        except exceptions as e:
            if attempt >= retries:
                raise
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_backoff)
            attempt += 1
