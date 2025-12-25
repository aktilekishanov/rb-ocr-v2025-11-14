import json
import ssl
import urllib.error
import urllib.request
from http import HTTPStatus
from typing import Any, Dict

from core.settings import llm_settings
from pipeline.core.config import ERROR_BODY_MAX_CHARS, LLM_REQUEST_TIMEOUT_SECONDS
from pipeline.core.exceptions import ExternalServiceError


_SSL_CONTEXT = ssl._create_unverified_context()


def _raise_llm_error(
    error_type: str,
    details: Dict[str, Any],
    exc: Exception,
) -> None:
    raise ExternalServiceError(
        service_name="LLM",
        error_type=error_type,
        details=details,
    ) from exc


def _read_error_body(err: urllib.error.HTTPError) -> str:
    try:
        return err.read().decode("utf-8")[:ERROR_BODY_MAX_CHARS]
    except Exception:
        return ""


def _build_request(payload: dict) -> urllib.request.Request:
    return urllib.request.Request(
        llm_settings.LLM_ENDPOINT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )


def ask_llm(
    prompt: str,
    *,
    model: str = "gpt-4o",
    temperature: float = 0.0,
    max_tokens: int = 500,
) -> str:
    """
    Call internal LLM endpoint and return raw response string.

    Raises:
        ExternalServiceError: On any network or service failure.
    """
    payload = {
        "Model": model,
        "Content": prompt,
        "Temperature": temperature,
        "MaxTokens": max_tokens,
    }

    request = _build_request(payload)

    try:
        with urllib.request.urlopen(
            request,
            context=_SSL_CONTEXT,
            timeout=LLM_REQUEST_TIMEOUT_SECONDS,
        ) as response:
            return response.read().decode("utf-8")

    except urllib.error.HTTPError as e:
        error_type = (
            "rate_limit"
            if e.code == HTTPStatus.TOO_MANY_REQUESTS
            else "error"
        )
        _raise_llm_error(
            error_type,
            {
                "http_code": e.code,
                "reason": str(e.reason),
                "body": _read_error_body(e),
            },
            e,
        )

    except urllib.error.URLError as e:
        reason = str(getattr(e, "reason", e))
        _raise_llm_error(
            "timeout" if "timeout" in reason.lower() else "unavailable",
            {"reason": reason},
            e,
        )

    except Exception as e:
        _raise_llm_error(
            "error",
            {"reason": f"Unexpected error: {e}"},
            e,
        )

    # for type checkers only
    return ""
