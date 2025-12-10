"""Resilience utilities for external service calls.

This module provides patterns for handling failures in distributed systems:
- Circuit Breaker: Prevents cascading failures
- Retry Logic: Handles transient errors
"""

from pipeline.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from pipeline.resilience.retry import retry_with_backoff, RetryConfig

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "retry_with_backoff",
    "RetryConfig",
]
