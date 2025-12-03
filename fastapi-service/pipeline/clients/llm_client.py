"""
Client for the internal ForteBank LLM completion endpoint.
"""

import json
import ssl
import urllib.request
import urllib.error
from typing import Optional


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
        with urllib.request.urlopen(req, context=context, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return raw
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            pass
        raise LLMHTTPError(
            f"HTTP {e.code} error from LLM endpoint: {e.reason}. Body: {error_body}"
        ) from e
    except urllib.error.URLError as e:
        raise LLMNetworkError(
            f"Network error connecting to LLM endpoint: {e.reason}"
        ) from e
    except ssl.SSLError as e:
        raise LLMNetworkError(
            f"SSL error connecting to LLM endpoint: {e}"
        ) from e
    except UnicodeDecodeError as e:
        raise LLMResponseError(
            f"Failed to decode LLM response as UTF-8: {e}"
        ) from e
    except Exception as e:
        raise LLMClientError(
            f"Unexpected error calling LLM endpoint: {e}"
        ) from e



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
