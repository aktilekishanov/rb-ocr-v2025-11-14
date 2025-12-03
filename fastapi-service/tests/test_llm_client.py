"""
Unit tests for the LLM client module.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
import urllib.error

from pipeline.clients.llm_client import (
    call_fortebank_llm,
    ask_llm,
    LLMClientError,
    LLMNetworkError,
    LLMHTTPError,
    LLMResponseError,
)


class TestCallFortebankLLM:
    """Tests for call_fortebank_llm function."""

    def test_successful_call(self):
        """Test successful LLM API call."""
        mock_response = {
            "choices": [{
                "message": {
                    "content": '{"document_type": "ID"}'
                }
            }]
        }
        mock_response_str = json.dumps(mock_response)

        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_context = MagicMock()
            mock_context.read.return_value = mock_response_str.encode('utf-8')
            mock_urlopen.return_value.__enter__.return_value = mock_context

            result = call_fortebank_llm("test prompt")
            
            assert result == mock_response_str
            assert mock_urlopen.called

    def test_http_error_handling(self):
        """Test HTTP error handling (4xx, 5xx)."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            error = urllib.error.HTTPError(
                url="test_url",
                code=500,
                msg="Internal Server Error",
                hdrs={},
                fp=None
            )
            error.read = MagicMock(return_value=b'{"error": "server error"}')
            mock_urlopen.side_effect = error

            with pytest.raises(LLMHTTPError) as exc_info:
                call_fortebank_llm("test prompt")
            
            assert "HTTP 500" in str(exc_info.value)
            assert "Internal Server Error" in str(exc_info.value)

    def test_network_error_handling(self):
        """Test network error handling."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            error = urllib.error.URLError("Connection refused")
            mock_urlopen.side_effect = error

            with pytest.raises(LLMNetworkError) as exc_info:
                call_fortebank_llm("test prompt")
            
            assert "Network error" in str(exc_info.value)

    def test_unicode_decode_error(self):
        """Test handling of invalid UTF-8 response."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_context = MagicMock()
            # Invalid UTF-8 sequence
            mock_context.read.return_value = b'\xff\xfe'
            mock_urlopen.return_value.__enter__.return_value = mock_context

            with pytest.raises(LLMResponseError) as exc_info:
                call_fortebank_llm("test prompt")
            
            assert "decode" in str(exc_info.value).lower()

    def test_custom_parameters(self):
        """Test call with custom parameters."""
        mock_response = '{"choices": []}'

        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_context = MagicMock()
            mock_context.read.return_value = mock_response.encode('utf-8')
            mock_urlopen.return_value.__enter__.return_value = mock_context

            result = call_fortebank_llm(
                prompt="custom prompt",
                model="gpt-4",
                temperature=0.7,
                max_tokens=1000
            )
            
            assert result == mock_response
            
            # Verify the request was made with correct parameters
            call_args = mock_urlopen.call_args
            request = call_args[0][0]
            payload = json.loads(request.data.decode('utf-8'))
            
            assert payload["Model"] == "gpt-4"
            assert payload["Content"] == "custom prompt"
            assert payload["Temperature"] == 0.7
            assert payload["MaxTokens"] == 1000


class TestAskLLM:
    """Tests for ask_llm function."""

    def test_returns_raw_response(self):
        """Test that ask_llm returns raw response from call_fortebank_llm."""
        expected_response = '{"choices": [{"message": {"content": "test"}}]}'

        with patch('pipeline.clients.llm_client.call_fortebank_llm') as mock_call:
            mock_call.return_value = expected_response

            result = ask_llm("test prompt")
            
            assert result == expected_response
            mock_call.assert_called_once_with(
                "test prompt",
                model="gpt-4o",
                temperature=0,
                max_tokens=500
            )

    def test_passes_parameters_correctly(self):
        """Test that ask_llm passes parameters to call_fortebank_llm."""
        with patch('pipeline.clients.llm_client.call_fortebank_llm') as mock_call:
            mock_call.return_value = '{"test": "response"}'

            ask_llm(
                prompt="custom",
                model="gpt-3.5",
                temperature=0.5,
                max_tokens=200
            )
            
            mock_call.assert_called_once_with(
                "custom",
                model="gpt-3.5",
                temperature=0.5,
                max_tokens=200
            )

    def test_propagates_exceptions(self):
        """Test that ask_llm propagates exceptions from call_fortebank_llm."""
        with patch('pipeline.clients.llm_client.call_fortebank_llm') as mock_call:
            mock_call.side_effect = LLMNetworkError("Network error")

            with pytest.raises(LLMNetworkError):
                ask_llm("test prompt")


class TestExceptionHierarchy:
    """Tests for exception hierarchy."""

    def test_exception_inheritance(self):
        """Test that all custom exceptions inherit from LLMClientError."""
        assert issubclass(LLMNetworkError, LLMClientError)
        assert issubclass(LLMHTTPError, LLMClientError)
        assert issubclass(LLMResponseError, LLMClientError)

    def test_can_catch_base_exception(self):
        """Test that base exception can catch all specific exceptions."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("test")

            try:
                call_fortebank_llm("test")
            except LLMClientError:
                # Should catch LLMNetworkError via base class
                pass
            else:
                pytest.fail("Should have raised LLMClientError or subclass")
