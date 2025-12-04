
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Tuple, Type, Union

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMRetryResult:
    """Container for a successful LLM call & validation."""
    raw_text: str
    parsed_json: Any  # dict/list
    validated: Any  # Pydantic validated dict


class LLMRetryError(RuntimeError):
    """Raised when all retry attempts fail."""
    pass


def call_llm_with_retries(
    *,
    user_prompt: str,
    system_prompt: str,
    send_func: Callable[..., str],
    pydantic_model: Optional[Type[BaseModel]] = None,
    # send_func kwargs (forwarded)
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    timeout: Optional[float] = None,
    # retry policy
    max_attempts: int = 4,
    initial_backoff: float = 1.0,
    max_backoff: float = 12.0,
    jitter_ratio: float = 0.15,
    # which exceptions to treat as transient (timeout/network/etc.)
    transient_exceptions: Tuple[Type[BaseException], ...] = (TimeoutError,),
    # Optional hook to inspect/transform the raw text before JSON parsing
    normalize_response: Optional[Callable[[str], str]] = None,
) -> LLMRetryResult:
    """
    Call an LLM with retries until JSON is valid and (optionally) passes Pydantic validation.

    Args:
        prompt: Fully rendered prompt text.
        send_func: Callable that actually sends the request, must return raw text.
            Signature example: send_func(prompt=..., model=..., temperature=..., timeout=...)
        pydantic_model: If provided, JSON will be validated against this model.
        model, temperature, timeout: Forwarded to send_func.
        max_attempts: Total attempts including the first.
        initial_backoff: First backoff (seconds) before retrying.
        max_backoff: Maximum backoff cap (seconds).
        jitter_ratio: Fractional jitter added to backoff (0.15 -> ±15%).
        transient_exceptions: Exception types that should trigger a retry.
        normalize_response: Optional function to clean/strip/repair the LLM text
            before json.loads (e.g., remove code fences).

    Returns:
        LLMRetryResult with (raw_text, parsed_json, validated_model or None).

    Raises:
        LLMRetryError after exhausting attempts.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    attempt = 0
    last_error: Optional[BaseException] = None

    while attempt < max_attempts:
        attempt += 1
        try:
            # 1) Call the LLM
            raw_text = send_func(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=temperature,
                timeout=timeout,
            )

            # 2) Optionally normalize (e.g., strip ```json fences)
            if normalize_response is not None:
                raw_text = normalize_response(raw_text)

            # 3) Parse JSON
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError as e:
                last_error = e
                _log_retry_issue(
                    stage="json-parse",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    err=e,
                    detail_preview=_preview(raw_text),
                )
                _sleep_with_backoff(attempt, initial_backoff, max_backoff, jitter_ratio)
                continue

            # 4) Pydantic validation (if requested)
            validated_instance = None
            if pydantic_model is not None:
                try:
                    validated_instance = pydantic_model.model_validate(parsed).model_dump()
                except ValidationError as e:
                    last_error = e
                    _log_retry_issue(
                        stage="pydantic-validate",
                        attempt=attempt,
                        max_attempts=max_attempts,
                        err=e,
                        detail_preview=_preview(parsed),
                    )
                    _sleep_with_backoff(attempt, initial_backoff, max_backoff, jitter_ratio)
                    continue
            else:
                validated_instance = parsed

            # Success
            return LLMRetryResult(
                raw_text=raw_text,
                parsed_json=parsed,
                validated=validated_instance,
            )

        except transient_exceptions as e:
            last_error = e
            _log_retry_issue(
                stage="llm-timeout/transient",
                attempt=attempt,
                max_attempts=max_attempts,
                err=e,
                detail_preview=None,
            )
            _sleep_with_backoff(attempt, initial_backoff, max_backoff, jitter_ratio)
            continue

        except Exception as e:
            # Unknown error — decide to retry or fail fast. Here we retry, but you can
            # restrict this to only certain exceptions if you prefer.
            last_error = e
            _log_retry_issue(
                stage="llm-unknown",
                attempt=attempt,
                max_attempts=max_attempts,
                err=e,
                detail_preview=None,
            )
            _sleep_with_backoff(attempt, initial_backoff, max_backoff, jitter_ratio)
            continue

    # Exhausted
    raise LLMRetryError(
        f"LLM call failed after {max_attempts} attempts. Last error: {repr(last_error)}"
    )


# --- helpers -----------------------------------------------------------------

def _sleep_with_backoff(attempt: int, initial: float, maximum: float, jitter_ratio: float) -> None:
    base = min(maximum, initial * (2 ** (attempt - 1)))
    jitter = base * jitter_ratio
    delay = max(0.0, random.uniform(base - jitter, base + jitter))
    time.sleep(delay)


def _preview(obj: Union[str, dict, list], length: int = 50) -> str:
    try:
        if isinstance(obj, (dict, list)):
            s = json.dumps(obj, ensure_ascii=False)[:length]
        else:
            s = str(obj)[:length]
        return s + ("…" if len(s) == length else "")
    except Exception:
        return "<unpreviewable>"


def _log_retry_issue(
    *,
    stage: str,
    attempt: int,
    max_attempts: int,
    err: BaseException,
    detail_preview: Optional[str],
) -> None:
    msg = f"[LLM retry] Stage={stage} attempt={attempt}/{max_attempts} error={type(err).__name__}: {err}"
    if detail_preview:
        msg += f" | preview={detail_preview}"
    if attempt < max_attempts:
        logger.warning(msg)
    else:
        logger.error(msg)

def strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # remove the first fence line
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1 :]
    if t.endswith("```"):
        t = t[:-3]
    return t.strip()
