import json
from typing import Any, Dict


def parse_ocr_output(obj: dict) -> list[dict]:
    """Extract text pages from OCR result.
    
    Args:
        obj: Already-unwrapped OCR result object with structure data.pages
             (NOT result.data.pages - that's already unwrapped by ask_tesseract)
        
    Returns:
        List of dicts with page_number and text keys
    """
    # obj is already the inner "result" object, so we access data.pages directly
    pages = obj.get("data", {}).get("pages", [])
    parsed = []
    for p in pages:
        if isinstance(p, dict):
            parsed.append({
                "page_number": p.get("page_number"),
                "text": p.get("text") or ""
            })
    return parsed


def parse_llm_output(raw: str) -> Dict[str, Any]:
    """
    Extract and parse the JSON dict contained inside LLM response["choices"][0]["message"]["content"].

    Returns:
        Parsed dict if valid, otherwise empty dict.
    """
    if not raw:
        return {}

    try:
        outer = json.loads(raw)
        msg = (
            outer.get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )
        if not isinstance(msg, str):
            return {}

        # Try to parse inner JSON from LLM content
        inner = json.loads(msg)
        return inner if isinstance(inner, dict) else {}

    except Exception:
        return {}
