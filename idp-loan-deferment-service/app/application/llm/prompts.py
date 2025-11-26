from __future__ import annotations


def build_doc_type_prompt(text: str) -> str:
    return (
        "You are a document classifier. Read the document text and output ONLY a compact JSON with keys "
        '"doc_type" (a short snake_case identifier, e.g., "loan_deferment") and "confidence" (0..1). '
        "Do not include any other text.\n\nDOCUMENT:\n" + text +
        "\n\nRESPONSE JSON EXAMPLE:\n{\"doc_type\":\"loan_deferment\",\"confidence\":0.9}"
    )


def build_extract_prompt(text: str) -> str:
    return (
        "Extract structured fields from the following document. Output ONLY a compact JSON with a single key "
        '"fields" whose value is an object mapping field names to values. No extra commentary. '
        "\n\nDOCUMENT:\n" + text +
        "\n\nRESPONSE JSON EXAMPLE:\n{\"fields\": {\"fio\": \"John Doe\"}}"
    )
