"""Unit tests for retry logic with exponential backoff."""

import pytest
import time
from unittest.mock import Mock, call
from pipeline.resilience.retry import retry_with_backoff, RetryConfig


# Test fixtures
call_count = 0


def reset_call_count():
    """Reset global call counter."""
    global call_count
    call_count = 0


def always_fails():
    """Always raises exception."""
    raise ValueError("Service error")


def succeeds_immediately():
    """Always succeeds."""
    return "success"


def fails_twice_then_succeeds():
    """Fails first 2 times, succeeds on 3rd."""
    global call_count
    call_count += 1
    if call_count < 3:
        raise TimeoutError(f"Timeout attempt {call_count}")
    return f"Success on attempt {call_count}"


def fails_once_then_succeeds():
    """Fails once, then succeeds."""
    global call_count
    call_count += 1
    if call_count == 1:
        raise ConnectionError("Connection failed")
    return "success"


class TestRetryBasics:
    """Tests for basic retry functionality."""
    
    def test_immediate_success_no_retry(self):
        """Test function that succeeds immediately doesn't retry."""
        result = retry_with_backoff(
            succeeds_immediately,
            RetryConfig(max_attempts=3),
            (Exception,)
        )
        assert result == "success"
    
    def test_retries_on_specified_exception(self):
        """Test retry happens on specified exception type."""
        reset_call_count()
        
        result = retry_with_backoff(
            fails_once_then_succeeds,
            RetryConfig(max_attempts=3, initial_delay_seconds=0.1),
            (ConnectionError,)
        )
        
        assert result == "success"
        assert call_count == 2  # Failed once, succeeded on 2nd
    
    def test_raises_after_max_attempts(self):
        """Test raises exception after exhausting retries."""
        with pytest.raises(ValueError) as exc_info:
            retry_with_backoff(
                always_fails,
                RetryConfig(max_attempts=3, initial_delay_seconds=0.1),
                (ValueError,)
            )
        
        assert "Service error" in str(exc_info.value)
    
    def test_does_not_retry_on_other_exceptions(self):
        """Test does not retry on non-specified exceptions."""
        def raises_type_error():
            raise TypeError("Wrong type")
        
        # Only retry on ValueError, not TypeError
        with pytest.raises(TypeError):
            retry_with_backoff(
                raises_type_error,
                RetryConfig(max_attempts=3),
                (ValueError,)
            )


class TestRetryConfiguration:
    """Tests for retry configuration."""
    
    def test_max_attempts_honored(self):
        """Test max_attempts configuration is honored."""
        reset_call_count()
        
        with pytest.raises(TimeoutError):
            retry_with_backoff(
                fails_twice_then_succeeds,
                RetryConfig(max_attempts=2, initial_delay_seconds=0.1),
                (TimeoutError,)
            )
        
        assert call_count == 2  # Should stop after 2 attempts
    
    def test_exponential_backoff_timing(self):
        """Test exponential backoff increases delay."""
        reset_call_count()
        
        start_time = time.time()
        
        with pytest.raises(TimeoutError):
            retry_with_backoff(
                fails_twice_then_succeeds,
                RetryConfig(
                    max_attempts=2,
                    initial_delay_seconds=0.5,
                    exponential_base=2.0,
                    jitter=False  # Disable jitter for predictable timing
                ),
                (TimeoutError,)
            )
        
        elapsed = time.time() - start_time
        
        # First retry: 0.5s delay
        # Total should be >= 0.5s (we had 2 attempts, 1 delay)
        assert elapsed >= 0.5
        assert elapsed < 1.0  # Shouldn't take too long
    
    def test_max_delay_cap(self):
        """Test delay is capped at max_delay_seconds."""
        reset_call_count()
        
        config = RetryConfig(
            max_attempts=3,  # Reduced to match what will actually fail
            initial_delay_seconds=10.0,
            max_delay_seconds=0.2,
            exponential_base=2.0,
            jitter=False
        )
        
        start_time = time.time()
        
        with pytest.raises(ValueError):  # Using always_fails which raises ValueError
            retry_with_backoff(
                always_fails,
                config,
                (ValueError,)
            )
        
        elapsed = time.time() - start_time
        
        # Even with initial_delay=10s, max_delay=0.2s should cap it
        # 3 attempts = 2 retries = 2 * 0.2s = 0.4s max
        assert elapsed < 1.0
    
    def test_jitter_adds_randomness(self):
        """Test jitter adds randomness to delays."""
        reset_call_count()
        
        # Run multiple times and collect delays
        delays = []
        
        for _ in range(5):
            reset_call_count()
            start_time = time.time()
            
            with pytest.raises(TimeoutError):
                retry_with_backoff(
                    fails_twice_then_succeeds,
                    RetryConfig(
                        max_attempts=2,
                        initial_delay_seconds=0.5,
                        jitter=True
                    ),
                    (TimeoutError,)
                )
            
            delays.append(time.time() - start_time)
        
        # With jitter, delays should vary
        # (Without jitter, they'd all be the same)
        assert len(set([round(d, 2) for d in delays])) > 1


class TestRetryWithMultipleExceptions:
    """Tests for retrying on multiple exception types."""
    
    def test_retry_on_multiple_exception_types(self):
        """Test retry works with multiple exception types."""
        reset_call_count()
        
        def raises_different_errors():
            global call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("Timeout")
            elif call_count == 2:
                raise ConnectionError("Connection failed")
            else:
                return "success"
        
        result = retry_with_backoff(
            raises_different_errors,
            RetryConfig(max_attempts=3, initial_delay_seconds=0.1),
            (TimeoutError, ConnectionError)
        )
        
        assert result == "success"
        assert call_count == 3


class TestRetryEdgeCases:
    """Tests for edge cases and error conditions."""
    
    def test_single_attempt_no_retry(self):
        """Test max_attempts=1 doesn't retry."""
        with pytest.raises(ValueError):
            retry_with_backoff(
                always_fails,
                RetryConfig(max_attempts=1),
                (ValueError,)
            )
    
    def test_zero_initial_delay(self):
        """Test retry works with zero initial delay."""
        reset_call_count()
        
        start_time = time.time()
        
        result = retry_with_backoff(
            fails_once_then_succeeds,
            RetryConfig(max_attempts=3, initial_delay_seconds=0.0),
            (ConnectionError,)
        )
        
        elapsed = time.time() - start_time
        
        assert result == "success"
        assert elapsed < 0.1  # Should be nearly instant
    
    def test_function_with_arguments(self):
        """Test retry works with function arguments."""
        def add_numbers(a, b):
            global call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First call fails")
            return a + b
        
        reset_call_count()
        
        result = retry_with_backoff(
            add_numbers,
            RetryConfig(max_attempts=2, initial_delay_seconds=0.1),
            (ValueError,),
            5, 3  # Arguments to add_numbers
        )
        
        assert result == 8
    
    def test_function_with_kwargs(self):
        """Test retry works with keyword arguments."""
        def greet(name, greeting="Hello"):
            global call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First call fails")
            return f"{greeting}, {name}!"
        
        reset_call_count()
        
        result = retry_with_backoff(
            greet,
            RetryConfig(max_attempts=2, initial_delay_seconds=0.1),
            (ValueError,),
            name="World",
            greeting="Hi"
        )
        
        assert result == "Hi, World!"


class TestRetryLogging:
    """Tests for logging behavior (if applicable)."""
    
    def test_logs_retry_attempts(self, caplog):
        """Test retry attempts are logged."""
        reset_call_count()
        
        with pytest.raises(TimeoutError):
            retry_with_backoff(
                fails_twice_then_succeeds,
                RetryConfig(max_attempts=2, initial_delay_seconds=0.1),
                (TimeoutError,)
            )
        
        # Should have warning log for retry
        assert any("Retrying" in record.message for record in caplog.records)
        assert any("failed" in record.message.lower() for record in caplog.records)


class TestRetryRealWorld:
    """Real-world scenario tests."""
    
    def test_api_call_retry_scenario(self):
        """Test typical API call retry scenario."""
        reset_call_count()
        
        def call_api(endpoint):
            """Simulates unreliable API call."""
            global call_count
            call_count += 1
            
            if call_count <= 2:
                raise ConnectionError(f"Connection failed (attempt {call_count})")
            
            return {"status": "success", "data": f"Response from {endpoint}"}
        
        result = retry_with_backoff(
            call_api,
            RetryConfig(
                max_attempts=5,
                initial_delay_seconds=0.1,
                exponential_base=2.0,
                jitter=True
            ),
            (ConnectionError, TimeoutError),
            "/api/data"
        )
        
        assert result["status"] == "success"
        assert call_count == 3


class TestRetryConfigDefaults:
    """Tests for RetryConfig default values."""
    
    def test_default_config_values(self):
        """Test RetryConfig has sensible defaults."""
        config = RetryConfig()
        
        assert config.max_attempts == 3
        assert config.initial_delay_seconds == 1.0
        assert config.max_delay_seconds == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
