"""Retry logic with exponential backoff and jitter.

Provides resilient retry mechanisms for handling transient failures in
external service calls.

Example:
    >>> from pipeline.resilience.retry import retry_with_backoff, RetryConfig
    >>> config = RetryConfig(max_attempts=3, initial_delay_seconds=1.0)
    >>> result = retry_with_backoff(
    ...     ask_llm_service,
    ...     config,
    ...     (httpx.TimeoutException, httpx.HTTPStatusError),
    ...     prompt="Extract data"
    ... )
"""

import time
import random
from typing import Callable, Any, Type, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry logic.
    
    Attributes:
        max_attempts: Maximum number of attempts (including initial)
        initial_delay_seconds: Initial delay before first retry
        max_delay_seconds: Maximum delay between retries
        exponential_base: Base for exponential backoff (delay *= base ** attempt)
        jitter: Whether to add random jitter to delays
    """
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


def retry_with_backoff(
    func: Callable[..., Any],
    config: RetryConfig,
    retryable_exceptions: Tuple[Type[Exception], ...],
    *args,
    **kwargs
) -> Any:
    """Retry function with exponential backoff and jitter.
    
    Args:
        func: Function to execute
        config: Retry configuration
        retryable_exceptions: Tuple of exception types that trigger retry
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func
        
    Returns:
        Result from successful function call
        
    Raises:
        Last exception if all retry attempts fail
        
    Example:
        >>> config = RetryConfig(max_attempts=3)
        >>> result = retry_with_backoff(
        ...     call_api,
        ...     config,
        ...     (TimeoutError, ConnectionError),
        ...     url="https://api.example.com"
        ... )
    """
    
    last_exception = None
    
    for attempt in range(config.max_attempts):
        try:
            return func(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e
            
            # Don't retry if this was the last attempt
            if attempt == config.max_attempts - 1:
                logger.error(
                    f"All {config.max_attempts} retry attempts failed",
                    extra={"exception": str(e)},
                    exc_info=True
                )
                raise
            
            # Calculate delay with exponential backoff
            delay = min(
                config.initial_delay_seconds * (config.exponential_base ** attempt),
                config.max_delay_seconds
            )
            
            # Add jitter to prevent thundering herd
            if config.jitter:
                delay = delay * (0.5 + random.random())  # Random between 50% and 150%
            
            logger.warning(
                f"Attempt {attempt + 1}/{config.max_attempts} failed: {type(e).__name__}: {e}. "
                f"Retrying in {delay:.2f}s...",
                extra={
                    "attempt": attempt + 1,
                    "max_attempts": config.max_attempts,
                    "delay_seconds": delay,
                    "exception_type": type(e).__name__,
                }
            )
            
            time.sleep(delay)
    
    # This should never be reached due to the raise in the loop,
    # but included for type checking
    if last_exception:
        raise last_exception
