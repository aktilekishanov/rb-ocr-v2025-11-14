"""
Normalize raw provider-specific LLM responses into a single JSON dict.

This module handles multi-line JSONL-style responses and OpenAI-like
envelopes, extracting the first usable dict for downstream typed models.
"""

import json
import os
from typing import Any

from pipeline.utils.io_utils import write_json


def _try_parse_inner_json(text: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def _extract_from_openai_like(obj: dict[str, Any]) -> dict[str, Any] | None:
    choices = obj.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            msg = first_choice.get("message")
            if isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, str):
                    inner = _try_parse_inner_json(content)
                    if isinstance(inner, dict):
                        return inner
            text = first_choice.get("text")
            if isinstance(text, str):
                inner = _try_parse_inner_json(text)
                if isinstance(inner, dict):
                    return inner
    # Some providers include direct top-level content
    content = obj.get("content")
    if isinstance(content, str):
        inner = _try_parse_inner_json(content)
        if isinstance(inner, dict):
            return inner
    return None


def _parse_llm_response(raw: str) -> dict[str, Any]:
    """Parse raw LLM output into filtered JSON dict.

    Strategy per line:
      1) If dict: try to extract OpenAI-like inner JSON (choices[0].message.content).
      2) If dict: else use the dict as-is (skipping provider prompt-echo dicts).
      3) If string: try to parse it as JSON dict or nested JSON string.

    The first successful dict is returned. If none is found, an empty object
    is returned instead.

    Args:
        raw: Raw LLM response string (may be multi-line JSONL)

    Returns:
        Filtered dict extracted from response, or empty dict if none found
    """
    result_obj: dict[str, Any] = {}

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            # maybe a JSON string
            inner = _try_parse_inner_json(line)
            if isinstance(inner, dict):
                result_obj = inner
                break
            continue

        if isinstance(obj, dict):
            inner = _extract_from_openai_like(obj)
            if isinstance(inner, dict):
                result_obj = inner
                break
            # Skip provider prompt-echo dicts (they usually contain 'Model' and 'Content')
            if "Model" in obj and "Content" in obj:
                continue
            # Otherwise, accept the dict as-is
            result_obj = obj
            break
        elif isinstance(obj, str):
            inner = _try_parse_inner_json(obj)
            if isinstance(inner, dict):
                result_obj = inner
                break

    return result_obj


def filter_llm_generic_response(input_path: str, output_dir: str, filename: str) -> str:
    """Filter raw LLM output into a single JSON dict.

    Reads raw LLM response from file, parses it to extract usable JSON,
    and writes the filtered result to output file.

    This is where provider-specific envelope differences are normalized
    before we validate into typed DTO models.

    Args:
        input_path: Path to raw LLM response file
        output_dir: Directory to write filtered output
        filename: Name of output file

    Returns:
        Full path to the written filtered file
    """
    with open(input_path, encoding="utf-8") as f:
        raw = f.read()

    result_obj = _parse_llm_response(raw)
    out_path = os.path.join(output_dir, filename)
    write_json(out_path, result_obj)
    return out_path
