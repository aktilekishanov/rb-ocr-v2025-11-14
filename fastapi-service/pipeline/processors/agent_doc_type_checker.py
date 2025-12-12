"""
LLM-based document type checker processor.

Builds a prompt from OCR pages, calls the internal LLM client, and
returns the raw JSON response string to be filtered downstream.

Prompt text is stored under `pipeline/prompts/dtc/` and is versioned as
`{version}.prompt.txt`. The template is expected to contain exactly one
`{}` placeholder where the JSON representation of OCR pages will be
injected.
"""

import json

from pipeline.clients.llm_client import ask_llm


DTC_PROMPT_V1 = """You are a deterministic OCR document-type classifier.
Analyze the OCR text and output ONLY the following JSON object (no extra text):
{
  "single_doc_type": true | false,
  "confidence: number [0...100]",
  "detected_doc_types": [ "..." ],
  "reasoning": "..."
  "doc_type_known": true | false
}
No extra text or commentary outside the JSON.

Semantics:
- detected_doc_types: canonicalized titles (best-first). If none, output an empty array.
- single_doc_type: if detected_doc_types contains =< 1 type → true, otherwise → false.
- doc_type_known: true ONLY if the top candidate is in the following Dictionary; false for unknown/ambiguous types.
- confidence: coarse confidence for the top candidate (diagnostics only; do not derive doc_type_known from it).
- reasoning: brief explanation for the decision.

---

## CLASSIFICATION ALGORITHM (strict order)

### 1. Noise Filtering

Ignore any of the following — they NEVER create new document types:
* OCR artifacts, partial English words, mixed-language fragments
* Dates, form numbers, signatures, translations, page numbers, headers/footers
* Repetitions of the same title in another language (e.g. Kazakh ↔ Russian)

### 2. Candidate Title Detection

Search the **first 15 non-empty lines** for possible document titles.
A line is a title if it contains or resembles words like:
**ПРИКАЗ, СПРАВКА, ЛИСТ, ВЫПИСКА, ЗАКЛЮЧЕНИЕ, УВЕДОМЛЕНИЕ**
or their Kazakh equivalents (**БҰЙРЫҚ, АНЫҚТАМА, ХАТТАМА, ХАБАРЛАМА**).

### 3. Canonical Document Types (reference list)

Fuzzy-match (Levenshtein ≥ 0.8) each candidate title to one of these canonical types from Dictionary:
1. Лист временной нетрудоспособности (больничный лист)
2. Приказ о выходе в декретный отпуск по уходу за ребенком
3. Справка о выходе в декретный отпуск по уходу за ребенком
4. Выписка из стационара (выписной эпикриз)
5. Больничный лист на сопровождающего (если предусмотрено)
6. Заключение врачебно-консультативной комиссии (ВКК)
7. Справка об инвалидности
8. Справка о степени утраты общей трудоспособности
9. Приказ о расторжении трудового договора
10. Справка о расторжении трудового договора
11. Справка о регистрации в качестве безработного
12. Приказ работодателя о предоставлении отпуска без сохранения заработной платы
13. Справка о неполучении доходов
14. Уведомление о регистрации в качестве лица, ищущего работу
15. Лица, зарегистрированные в качестве безработных

NOTE:
**Important semantic aliases (normalize these as identical):**
* "о предоставлении отпуска по уходу за ребенком"
* "о выходе в декретный отпуск по уходу за ребенком"
* "о предоставлении декретного отпуска"
* "Бала күтіміне байланысты жалақысы сақталмайтын демалыстар беру туралы"

All refer to canonical type either:
**Приказ о выходе в декретный отпуск по уходу за ребенком**
OR
**Справка о выходе в декретный отпуск по уходу за ребенком**

### 4. Normalization

Merge duplicates, translations, or paraphrases describing the same purpose.
If all detected titles are linguistic variants or synonyms of one canonical type → treat as **one** document → `single_doc_type = true`.

### 5. Distinct Document Detection
If two or more **different canonical types** are present (e.g. "Приказ о расторжении трудового договора" and "Справка о расторжении трудового договора") → `single_doc_type = false`.
Before declaring "multiple types," confirm that they represent **different legal purposes**, not wording variants or translations.

### 6. Issuer Check

If the text shows clearly unrelated issuers (different organizations or ministries), and each is tied to a distinct canonical type → `single_doc_type = false`.
Otherwise, ignore repeated issuer mentions.

### 7. Default Safety

- If uncertain, noisy, or ambiguous → default to
{
"single_doc_type": true,
"detected_doc_types": [...]
}
- If confidence is < 90 →
{
"single_doc_type": true,
"detected_doc_types": [...]
}

---

### 8. Output Rules

* Return **exactly one** valid JSON object.
* Do **NOT** include markdown formatting, code fences, explanations.
* Do **NOT** include ```json formatting
* JSON keys and string values must be enclosed in double quotes.

---

### TEXT FOR ANALYSIS
{}
"""


def check_single_doc_type(pages_obj: dict) -> str:
    """
    Run the LLM doc-type classifier for a set of OCR pages.

    Args:
      pages_obj: Normalized OCR pages object (as produced by filter_ocr_response).

    Returns:
      Raw LLM response string, expected to contain JSON that will be filtered
      by the generic LLM response filter.
    """
    pages_json_str = json.dumps(pages_obj, ensure_ascii=False)
    if not pages_json_str:
        return ""
    prompt = DTC_PROMPT_V1.replace("{}", pages_json_str, 1)
    return ask_llm(prompt)
