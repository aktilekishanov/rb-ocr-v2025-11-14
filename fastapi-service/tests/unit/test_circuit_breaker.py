"""Unit tests for circuit breaker pattern."""

import pytest
import time
from pipeline.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from pipeline.core.exceptions import ExternalServiceError


def failing_func():
    """Always fails."""
    raise Exception("Service unavailable")


def succeeding_func():
    """Always succeeds."""
    return "success"


call_count = 0

def sometimes_failing_func():
    """Fails first 3 times, then succeeds."""
    global call_count
    call_count += 1
    if call_count <= 3:
        raise Exception(f"Failure {call_count}")
    return f"Success after {call_count} calls"


class TestCircuitBreakerBasics:
    """Tests for basic circuit breaker functionality."""
    
    def test_circuit_breaker_creation(self):
        """Test CircuitBreaker can be created."""
        cb = CircuitBreaker("test", CircuitBreakerConfig())
        assert cb.name == "test"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
    
    def test_successful_call_in_closed_state(self):
        """Test successful calls work in CLOSED state."""
        cb = CircuitBreaker("test", CircuitBreakerConfig())
        result = cb.call(succeeding_func)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0


class TestCircuitBreakerStateTransitions:
    """Tests for circuit breaker state transitions."""
    
    def test_opens_after_failure_threshold(self):
        """Test circuit opens after reaching failure threshold."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        
        # First 2 failures - circuit stays closed
        for i in range(2):
            with pytest.raises(Exception):
                cb.call(failing_func)
        
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 2
        
        # 3rd failure - circuit opens
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3
    
    def test_rejects_requests_when_open(self):
        """Test circuit rejects requests when OPEN."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=1))
        
        # Open the circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
        
        # Should reject even successful function
        with pytest.raises(ExternalServiceError) as exc_info:
            cb.call(succeeding_func)
        
        error = exc_info.value
        assert error.http_status == 503  # Service Unavailable
        assert "circuit_open" in error.error_code.lower()
        assert "OPEN" in error.details["message"]
    
    def test_transitions_to_half_open_after_timeout(self):
        """Test circuit transitions to HALF_OPEN after timeout."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=1,
            timeout_seconds=1,
            success_threshold=2
        ))
        
        # Open circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
        
        # Wait for timeout
        time.sleep(1.1)
        
        # Next call should transition to HALF_OPEN
        result = cb.call(succeeding_func)
        assert result == "success"
        assert cb.state == CircuitState.HALF_OPEN
    
    def test_closes_after_success_threshold_in_half_open(self):
        """Test circuit closes after success threshold in HALF_OPEN."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=1,
            timeout_seconds=1,
            success_threshold=2
        ))
        
        # Open circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        # Wait and transition to HALF_OPEN
        time.sleep(1.1)
        
        # First success in HALF_OPEN
        result = cb.call(succeeding_func)
        assert result == "success"
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.success_count == 1
        
        # Second success closes circuit
        result = cb.call(succeeding_func)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0
    
    def test_reopens_on_failure_in_half_open(self):
        """Test circuit re-opens on failure in HALF_OPEN state."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=1,
            timeout_seconds=1
        ))
        
        # Open circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        # Wait and transition to HALF_OPEN
        time.sleep(1.1)
        cb.call(succeeding_func)  # Now in HALF_OPEN
        
        assert cb.state == CircuitState.HALF_OPEN
        
        # Failure in HALF_OPEN re-opens circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerConfiguration:
    """Tests for circuit breaker configuration."""
    
    def test_custom_failure_threshold(self):
        """Test custom failure threshold."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=5))
        
        # Should stay closed for 4 failures
        for _ in range(4):
            with pytest.raises(Exception):
                cb.call(failing_func)
        
        assert cb.state == CircuitState.CLOSED
        
        # 5th failure opens circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
    
    def test_custom_success_threshold(self):
        """Test custom success threshold in HALF_OPEN."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=1,
            timeout_seconds=1,
            success_threshold=3
        ))
        
        # Open circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        time.sleep(1.1)
        
        # Need 3 successes to close
        for i in range(2):
            cb.call(succeeding_func)
            assert cb.state == CircuitState.HALF_OPEN
        
        # 3rd success closes circuit
        cb.call(succeeding_func)
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerHelpers:
    """Tests for circuit breaker helper methods."""
    
    def test_manual_reset(self):
        """Test manual reset of circuit breaker."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=1))
        
        # Open circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
        
        # Manual reset
        cb.reset()
        
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0
    
    def test_get_state(self):
        """Test get_state returns current state information."""
        cb = CircuitBreaker("TestService", CircuitBreakerConfig(failure_threshold=2))
        
        state = cb.get_state()
        
        assert state["name"] == "TestService"
        assert state["state"] == "closed"
        assert state["failure_count"] == 0
        assert state["success_count"] == 0
        assert state["last_failure_time"] is None
        assert state["time_until_retry"] == 0
    
    def test_get_state_when_open(self):
        """Test get_state when circuit is OPEN."""
        cb = CircuitBreaker("TestService", CircuitBreakerConfig(
            failure_threshold=1,
            timeout_seconds=60
        ))
        
        # Open circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        state = cb.get_state()
        
        assert state["state"] == "open"
        assert state["failure_count"] == 1
        assert state["last_failure_time"] is not None
        assert 50 < state["time_until_retry"] <= 60
    
    def test_time_until_retry_calculation(self):
        """Test time_until_retry decreases over time."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=1,
            timeout_seconds=3
        ))
        
        # Open circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        time1 = cb._time_until_retry()
        assert 2 <= time1 <= 3
        
        time.sleep(1)
        
        time2 = cb._time_until_retry()
        assert time2 < time1
        assert 1 <= time2 <= 2


class TestCircuitBreakerErrorPropagation:
    """Tests for error propagation through circuit breaker."""
    
    def test_original_exception_propagated_when_closed(self):
        """Test original exception is propagated when circuit is CLOSED."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=5))
        
        with pytest.raises(Exception) as exc_info:
            cb.call(failing_func)
        
        assert "Service unavailable" in str(exc_info.value)
    
    def test_circuit_open_exception_when_open(self):
        """Test ExternalServiceError raised when circuit is OPEN."""
        cb = CircuitBreaker("OCR", CircuitBreakerConfig(failure_threshold=1))
        
        # Open circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        # Should raise ExternalServiceError
        with pytest.raises(ExternalServiceError) as exc_info:
            cb.call(succeeding_func)
        
        error = exc_info.value
        assert error.error_code == "OCR_CIRCUIT_OPEN"
        assert error.details["message"] == "Circuit breaker is OPEN. Service unavailable."
        assert "retry_after" in error.details


class TestCircuitBreakerRealWorld:
    """Real-world scenario tests."""
    
    def test_service_recovery_scenario(self):
        """Test full recovery scenario: fail -> open -> recover -> close."""
        global call_count
        call_count = 0
        
        cb = CircuitBreaker("API", CircuitBreakerConfig(
            failure_threshold=3,
            timeout_seconds=1,
            success_threshold=2
        ))
        
        # Service fails 3 times -> circuit opens
        for _ in range(3):
            with pytest.raises(Exception):
                cb.call(sometimes_failing_func)
        
        assert cb.state == CircuitState.OPEN
        
        # Wait for timeout
        time.sleep(1.1)
        
        # Service recovered -> successes close circuit
        result1 = cb.call(sometimes_failing_func)
        assert cb.state == CircuitState.HALF_OPEN
        
        result2 = cb.call(sometimes_failing_func)
        assert cb.state == CircuitState.CLOSED
        
        # Normal operation resumed
        result3 = cb.call(sometimes_failing_func)
        assert cb.state == CircuitState.CLOSED
