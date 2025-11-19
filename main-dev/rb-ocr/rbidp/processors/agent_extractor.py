from rbidp.clients.gpt_client import ask_gpt
import json

PROMPT = """
You are an expert in multilingual document information extraction and normalization.
Your task is to analyze a noisy OCR text that may contain both Kazakh and Russian fragments.

Extract ONLY the following fields:

- fio: full name of the person (e.g. Иванов Иван Иванович). If the name appears in oblique case (e.g. Ивановой Марине Олеговне), convert it to nominative (e.g. Иванова Марина Олеговна). If both a full and abbreviated form exist, always select the full explicit version.
- doc_date: main issuance date in format DD.MM.YYYY, or null if missing.
- valid_until: DD.MM.YYYY only if the text explicitly states the end date of a period (e.g. «с DD.MM.YYYY … по DD.MM.YYYY»); otherwise null. Do not infer.

Rules:
- If several dates exist, choose the main issuance date (usually near the header or "№").
- Ignore duplicates or minor typos.
- When a value is missing, set it strictly to null.
- Do not invent or assume missing data.
- If both Russian and Kazakh versions exist, output result in Russian.

Output STRICTLY this JSON (no explanations, no extra text, no markdown fences):
{
  "fio": string | null,
  "doc_date": string | null,
  "valid_until": string | null
}

Text for analysis:
{}
"""

def extract_doc_data(pages_obj: dict) -> str:
    pages_json_str = json.dumps(pages_obj, ensure_ascii=False)
    if not pages_json_str:
        return ""
    prompt = PROMPT.replace("{}", pages_json_str, 1)
    return ask_gpt(prompt)