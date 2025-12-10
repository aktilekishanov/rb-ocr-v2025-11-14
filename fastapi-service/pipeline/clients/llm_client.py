"""
Client for the internal ForteBank LLM completion endpoint.
"""

import json
import ssl
import urllib.request
import urllib.error
from typing import Optional
from http import HTTPStatus

from pipeline.core.config import (
    LLM_REQUEST_TIMEOUT_SECONDS,
    ERROR_BODY_MAX_CHARS,
)


class LLMClientError(Exception):
    """Base exception for LLM client errors."""
    pass


class LLMNetworkError(LLMClientError):
    """Raised when network/connection errors occur."""
    pass


class LLMHTTPError(LLMClientError):
    """Raised when HTTP errors occur (4xx, 5xx)."""
    pass


class LLMResponseError(LLMClientError):
    """Raised when response parsing fails."""
    pass


def call_fortebank_llm(
    prompt: str, model: str = "gpt-4o", temperature: float = 0, max_tokens: int = 500
) -> str:
    """
    Calls the internal ForteBank LLM endpoint and returns the model's response as a string.
    
    Args:
        prompt: The prompt text to send to the LLM.
        model: The model name (default: "gpt-4o").
        temperature: Sampling temperature (default: 0 for deterministic).
        max_tokens: Maximum tokens in response (default: 500).
    
    Returns:
        Raw JSON response string from the LLM endpoint.
    
    Raises:
        LLMNetworkError: If network/connection errors occur.
        LLMHTTPError: If HTTP errors occur (4xx, 5xx).
        LLMResponseError: If response cannot be read or decoded.
    """

    url = "https://dl-ai-dev-app01-uv01.fortebank.com/openai/payment/out/completions"
    payload = {
        "Model": model,
        "Content": prompt,
        "Temperature": temperature,
        "MaxTokens": max_tokens,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", "Accept": "*/*"}, method="POST"
    )

    # WORKAROUND: ignore SSL verification for dev DMZ endpoint (self-signed certs).
    # SECURITY: this must be revisited for production deployments.
    context = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(req, context=context, timeout=LLM_REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
            return raw
    except urllib.error.HTTPError as http_err:
        error_body = ""
        try:
            error_body = http_err.read().decode("utf-8")
        except Exception:
            pass
        
        from pipeline.core.exceptions import ExternalServiceError
        
        if http_err.code == HTTPStatus.TOO_MANY_REQUESTS:
            raise ExternalServiceError(
                service_name="LLM",
                error_type="rate_limit",
                details={
                    "http_code": http_err.code,
                    "reason": str(http_err.reason),
                    "body": error_body[:ERROR_BODY_MAX_CHARS],
                }
            ) from http_err
        elif HTTPStatus.INTERNAL_SERVER_ERROR <= http_err.code < 600:
            raise ExternalServiceError(
                service_name="LLM",
                error_type="error",
                details={
                    "http_code": http_err.code,
                    "reason": str(http_err.reason),
                    "body": error_body[:ERROR_BODY_MAX_CHARS],
                }
            ) from http_err
        else:
            raise LLMHTTPError(
                f"HTTP {http_err.code} error from LLM endpoint: {http_err.reason}. Body: {error_body[:200]}"
            ) from http_err
            
    except urllib.error.URLError as url_err:
        from pipeline.core.exceptions import ExternalServiceError
        
        error_str = str(url_err.reason) if hasattr(url_err, 'reason') else str(url_err)
        
        if "timeout" in error_str.lower() or "timed out" in error_str.lower():
            raise ExternalServiceError(
                service_name="LLM",
                error_type="timeout",
                details={"reason": error_str, "timeout_seconds": LLM_REQUEST_TIMEOUT_SECONDS}
            ) from url_err
        else:
            raise ExternalServiceError(
                service_name="LLM",
                error_type="unavailable",
                details={"reason": error_str}
            ) from url_err
            
    except ssl.SSLError as ssl_err:
        from pipeline.core.exceptions import ExternalServiceError
        raise ExternalServiceError(
            service_name="LLM",
            error_type="error",
            details={"reason": f"SSL error: {str(ssl_err)}"}
        ) from ssl_err
        
    except UnicodeDecodeError as decode_err:
        raise LLMResponseError(
            f"Failed to decode LLM response as UTF-8: {decode_err}"
        ) from decode_err
        
    except Exception as unexpected_err:
        raise LLMClientError(
            f"Unexpected error calling LLM endpoint: {unexpected_err}"
        ) from unexpected_err



def ask_llm(
    prompt: str, model: str = "gpt-4o", temperature: float = 0, max_tokens: int = 500
) -> str:
    """
    Calls the ForteBank LLM endpoint and returns the raw JSON response.
    
    The raw response is later processed by filter_llm_generic_response() 
    to extract the actual content from the provider-specific envelope.
    This separation allows the filter to handle all response format variations
    in a single place.
    
    Args:
        prompt: The prompt text to send to the LLM.
        model: The model name (default: "gpt-4o").
        temperature: Sampling temperature (default: 0 for deterministic).
        max_tokens: Maximum tokens in response (default: 500).
    
    Returns:
        Raw JSON response string from the LLM endpoint.
    """
    return call_fortebank_llm(prompt, model=model, temperature=temperature, max_tokens=max_tokens)
