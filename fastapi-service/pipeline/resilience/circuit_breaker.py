"""Circuit breaker pattern for external service calls.

The circuit breaker prevents cascading failures by monitoring error rates
and temporarily blocking requests when a service is failing.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Too many failures, requests blocked immediately
- HALF_OPEN: Testing if service recovered, limited requests allowed

Example:
    >>> breaker = CircuitBreaker("OCR", CircuitBreakerConfig(failure_threshold=5))
    >>> result = breaker.call(ask_ocr_service, file_path)
"""

from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Any, Optional, TypeVar
import logging

from pipeline.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker.

    Attributes:
        failure_threshold: Number of failures before opening circuit
        timeout_seconds: How long to keep circuit open before attempting reset
        success_threshold: Number of successes in HALF_OPEN to close circuit
    """

    failure_threshold: int = 5
    timeout_seconds: int = 60
    success_threshold: int = 2


class CircuitBreaker:
    """Circuit breaker for external service calls.

    Monitors error rates and prevents requests to failing services.

    Args:
        name: Service name for logging
        config: Circuit breaker configuration

    Example:
        >>> breaker = CircuitBreaker("OCR", CircuitBreakerConfig())
        >>> try:
        ...     result = breaker.call(ask_ocr, file_path)
        ... except ExternalServiceError as e:
        ...     # Circuit is open, service unavailable
        ...     pass
    """

    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None

    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            ExternalServiceError: If circuit is open or func fails
        """

        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to_half_open()
            else:
                raise ExternalServiceError(
                    service_name=self.name,
                    error_type="circuit_open",
                    details={
                        "message": f"Circuit breaker is OPEN. Service unavailable.",
                        "retry_after": self._time_until_retry(),
                    },
                )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return False

        elapsed = datetime.now() - self.last_failure_time
        return elapsed.total_seconds() >= self.config.timeout_seconds

    def _time_until_retry(self) -> int:
        """Seconds until circuit breaker may close."""
        if self.last_failure_time is None:
            return 0

        elapsed = datetime.now() - self.last_failure_time
        remaining = self.config.timeout_seconds - elapsed.total_seconds()
        return max(0, int(remaining))

    def _transition_to_half_open(self) -> None:
        """Transition from OPEN to HALF_OPEN state."""
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN state")

    def _on_success(self) -> None:
        """Handle successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self._transition_to_closed()

    def _on_failure(self) -> None:
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.state == CircuitState.HALF_OPEN:
            self._transition_to_open("re-OPENED after failure in HALF_OPEN")
        elif self.failure_count >= self.config.failure_threshold:
            self._transition_to_open(f"OPENED after {self.failure_count} failures")

    def _transition_to_closed(self) -> None:
        """Transition to CLOSED state (circuit working normally)."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        logger.info(f"Circuit breaker '{self.name}' CLOSED")

    def _transition_to_open(self, reason: str) -> None:
        """Transition to OPEN state (circuit blocking requests)."""
        self.state = CircuitState.OPEN
        logger.warning(f"Circuit breaker '{self.name}' {reason}")

    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state.

        Use with caution - typically only for testing or manual recovery.
        """
        self._transition_to_closed()
        logger.info(f"Circuit breaker '{self.name}' manually reset")

    def get_state(self) -> dict[str, Any]:
        """Get current circuit breaker state for monitoring.

        Returns:
            Dict containing state, failure count, and other metrics
        """
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time.isoformat()
            if self.last_failure_time
            else None,
            "time_until_retry": self._time_until_retry()
            if self.state == CircuitState.OPEN
            else 0,
        }
