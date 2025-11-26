from __future__ import annotations

import json
from typing import Any


def parse_doc_type(content: str) -> tuple[str, float | None, dict[str, Any]]:
    obj = json.loads(content)
    doc_type = obj.get("doc_type")
    if not isinstance(doc_type, str) or not doc_type:
        raise RuntimeError("LLM classify_doc_type missing doc_type")
    confidence = obj.get("confidence")
    try:
        conf_val = float(confidence) if confidence is not None else None
    except Exception:
        conf_val = None
    return doc_type, conf_val, obj


def parse_fields(content: str) -> tuple[dict[str, Any], dict[str, Any]]:
    obj = json.loads(content)
    fields = obj.get("fields", {})
    if not isinstance(fields, dict):
        raise RuntimeError("LLM extract_fields missing fields dict")
    return fields, obj
