"""
LLM-based data extractor processor.

Builds a prompt from OCR pages, calls the internal LLM client, and
returns the raw JSON response string for downstream filtering.

Prompt text is stored under `pipeline/prompts/extractor/` and is
versioned as `{version}.prompt.txt`. The template is expected to
contain exactly one `{}` placeholder where the JSON representation of
OCR pages will be injected.
"""

import json
from pathlib import Path

from pipeline.clients.llm_client import ask_llm


def _prompt_path(version: str = "v1") -> Path:
    return Path(__file__).resolve().parents[1] / "prompts" / "extractor" / f"{version}.prompt.txt"


def _load_prompt(version: str = "v1") -> str:
    """
    Load the versioned extractor prompt from disk.

    Args:
      version: Semantic prompt version such as `'v1'`.

    Returns:
      Raw prompt template text containing a single `{}` placeholder.
    """
    return _prompt_path(version).read_text(encoding="utf-8")


def extract_doc_data(pages_obj: dict) -> str:
    """
    Run the LLM extractor to obtain structured fields from OCR pages.

    Args:
      pages_obj: Normalized OCR pages object (as produced by filter_ocr_response).

    Returns:
      Raw LLM response string, expected to contain JSON that will be filtered
      by the generic LLM response filter.
    """
    pages_json_str = json.dumps(pages_obj, ensure_ascii=False)
    if not pages_json_str:
        return ""
    template = _load_prompt("v1")
    prompt = template.replace("{}", pages_json_str, 1)
    return ask_llm(prompt)
