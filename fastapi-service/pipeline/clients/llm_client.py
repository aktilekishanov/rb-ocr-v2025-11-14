import json
import os
import ssl
import urllib.error
import urllib.request
from http import HTTPStatus
from typing import Any

from pipeline.core.config import ERROR_BODY_MAX_CHARS, LLM_REQUEST_TIMEOUT_SECONDS
from pipeline.core.exceptions import ExternalServiceError


def _raise_llm_error(error_type: str, details: dict[str, Any], exc: Exception) -> None:
    raise ExternalServiceError(
        service_name="LLM",
        error_type=error_type,
        details=details,
    ) from exc


def ask_llm(
    prompt: str,
    model: str = "gpt-4o",
    temperature: float = 0,
    max_tokens: int = 500,
) -> str:
    """
    Call internal LLM endpoint and return raw JSON as string.

    Raises ExternalServiceError on any failure.
    """
    url = os.getenv("LLM_ENDPOINT_URL")

    payload = {
        "Model": model,
        "Content": prompt,
        "Temperature": temperature,
        "MaxTokens": max_tokens,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    context = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(
            req, context=context, timeout=LLM_REQUEST_TIMEOUT_SECONDS
        ) as r:
            return r.read().decode("utf-8")

    except urllib.error.HTTPError as e:
        # Extract body if possible
        try:
            body = e.read().decode("utf-8")[:ERROR_BODY_MAX_CHARS]
        except Exception:
            body = ""

        error_type = "rate_limit" if e.code == HTTPStatus.TOO_MANY_REQUESTS else "error"
        _raise_llm_error(
            error_type,
            {
                "http_code": e.code,
                "reason": str(e.reason),
                "body": body,
            },
            e,
        )

    except urllib.error.URLError as e:
        reason = getattr(e, "reason", str(e))
        is_timeout = "timeout" in str(reason).lower()
        _raise_llm_error(
            "timeout" if is_timeout else "unavailable",
            {"reason": str(reason)},
            e,
        )

    except Exception as e:
        _raise_llm_error(
            "error",
            {"reason": f"Unexpected error: {e}"},
            e,
        )

    # Unreachable, but keeps type checkers happy
    return ""
