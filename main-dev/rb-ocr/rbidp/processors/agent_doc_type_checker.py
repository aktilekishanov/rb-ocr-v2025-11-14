from rbidp.clients.gpt_client import ask_gpt
import json

# PROMPT = """
# SYSTEM INSTRUCTION:
# You are a precise document-type classifier. Your goal is to decide if the input OCR text represents ONE distinct document type or multiple.

# TASK:
# Return strictly a JSON object:
# {"single_doc_type": boolean}

# DEFINITIONS:
# - A *document type* = the document’s purpose (e.g., order, certificate, medical form, ID, decree).  
# - Different languages, duplicated headers, or OCR artifacts do NOT mean multiple documents.  
# - Only count as multiple if content clearly shows distinct purposes, issuers, people, or form numbers.

# DECISION RULES:
# 1. Same form number, same organization, same person, same purpose → true.  
# 2. Repeated headers, bilingual duplicates, or OCR noise → ignore → still true.  
# 3. Two or more unrelated forms (different document names, people, or cases) → false.  
# 4. If unclear, but all content aligns with one document → default to true.

# EXAMPLES:
# - "БҰЙРЫҚ / ПРИКАЗ" bilingual with same signature → true  
# - "ПРИКАЗ" + "СПРАВКА" → false  
# - Header repeated due to OCR → true  
# - Two different signatures for two people → false

# OUTPUT:
# Respond with only:
# {"single_doc_type": true}
# or
# {"single_doc_type": false}

# INPUT TEXT:
# {}
# """

# PROMPT = """
# You are a deterministic **OCR document-type classifier**.

# Your ONLY goal: decide if the OCR text represents ONE single document type or MULTIPLE distinct ones.

# Respond strictly with:
# {"single_doc_type": true}
# or
# {"single_doc_type": false}

# ---

# ### DECISION ALGORITHM (must follow in order)

# 1. **Noise Filtering**
# Ignore all OCR artifacts:
# - Random English words
# - Repeated headers
# - Mixed languages
# - Dates, years, or form numbers repeated
# These NEVER create new document types.

# 2. **Purpose Detection**
# Ask yourself: "Do all parts of the text revolve around the same general document purpose (e.g., medical certificate, order, ID)?"
# If yes → STOP → return {"single_doc_type": true}.

# 3. **Issuer Check**
# Are there clearly two unrelated organizations or issuers (e.g., two ministries or companies)?
# If not → still one document → return {"single_doc_type": true}.

# 4. **Form**
# Do you see two different form names (e.g., "026/y" and "027/y")?
# If not → still one document → return {"single_doc_type": true}.

# 5. **Contradiction Check**
# Only if you find **two clearly independent document purposes or issuers** → then and only then → {"single_doc_type": false}.

# If any step is unclear, uncertain, or noisy → default to {"single_doc_type": true}.

# 6. **Internal Control**
# Never output {"single_doc_type": false} unless you can quote in your mind two clearly different document titles.
# If no explicit title difference → always output {"single_doc_type": true}.
# **TRIPLE-CHECK**

# ---

# ### EXAMPLES
# true:
# - Medical form with repeated headers or bilingual lines.
# - Same form number repeated twice.
# - "Заключение комиссии" with random English tokens.

# false:
# - "ПРИКАЗ" followed by "СПРАВКА".
# - Two distinct ministries or organizations with unrelated context.

# ---

# ### OUTPUT FORMAT
# Output only:
# {"single_doc_type": true}
# or
# {"single_doc_type": false}
# No text, no reasoning, no punctuation.

# ---

# OCR INPUT:
# {}
# """

# PROMPT = """
# You are a deterministic OCR document-type classifier. Your ONLY output must be:
# {
# "single_doc_type": true | false,
# "detected_doc_types": [ str ],
# "reasoning": str
# }

# ---
 
# ### ALGORITHM (strict order)
 
# 1) **Noise filtering**

# Ignore:
# - OCR artifacts, random English words, repeated headers, translations, mixed languages, dates, and form numbers.
# These NEVER create new document types.
 
# 2) **Candidate title detection**
# Look for possible document titles in the first 15 non-empty lines.
# A title is any line containing words like "Приказ", "Справка", "Лист", "Выписка", "Заключение", "Уведомление", or their Kazakh equivalents, or matching any of the known types below.
 
# 3) **Known document types (canonical list)**

# Match titles fuzzily (Levenshtein ≥ 0.6) to these canonical document types:
# - Лист временной нетрудоспособности (больничный лист)
# - Приказ о выходе в декретный отпуск по уходу за ребенком
# - Справка о выходе в декретный отпуск по уходу за ребенком
# - Выписка из стационара (выписной эпикриз)
# - Больничный лист на сопровождающего (если предусмотрено)
# - Заключение врачебно-консультативной комиссии (ВКК)
# - Справка об инвалидности
# - Справка о степени утраты общей трудоспособности
# - Приказ о расторжении трудового договора
# - Справка о расторжении трудового договора
# - Справка о регистрации в качестве безработного
# - Приказ работодателя о предоставлении отпуска без сохранения заработной платы
# - Справка о неполучении доходов
# - Уведомление о регистрации в качестве лица, ищущего работу
# - Лица, зарегистрированные в качестве безработных
 
# 4) **Normalization**
# If multiple detected titles correspond to the same canonical document type (even in different languages or partial forms) → treat as one → output true.
 
# 5) **Distinct document detection**
# If two or more *different canonical types* appear (e.g., "Приказ о расторжении трудового договора" and "Справка о расторжении трудового договора") → output false.
 
# 6) **Issuer check**
# If two unrelated issuers (different organizations or ministries) are present and each is associated with a different canonical type → output false.
# Otherwise → ignore repetitions and translations.
 
# 7) **Default safety**
# If unclear, noisy, or ambiguous → default to {"single_doc_type": true}.
 
# 8) **Output**
# Output exactly one JSON object:
# {
# "single_doc_type": true | false,
# "detected_doc_types": [ str ],
# "reasoning": str
# }

# TEXT FOR ANALYSIS:
# {}
# """

PROMPT = """
You are a deterministic OCR document-type classifier.
Analyze the OCR text and output ONLY the following JSON object (no extra text):

{
  "detected_doc_types": [string],
  "single_doc_type": true | false,
  "confidence": 0-100,
  "reasoning": string,
  "doc_type_known": true | false
}

Semantics:
- detected_doc_types: canonicalized titles (best-first). If none, output an empty array.
- single_doc_type: whether the file contains exactly one distinct document type.
- doc_type_known: true ONLY if the top candidate is in the following Dictionary; false for unknown/ambiguous types.
- confidence: coarse confidence for the top candidate (diagnostics only; do not derive doc_type_known from it).
- reasoning: brief explanation for the decision.

Dictionary (canonical types):
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

Classification algorithm (strict order):
1) Noise filtering: ignore OCR artifacts, partial English words, mixed-language fragments, dates, form numbers, signatures, headers/footers, and translations. These never create new document types.
2) Candidate title detection: scan the first 15 non-empty lines for titles (e.g., ПРИКАЗ, СПРАВКА, ЛИСТ, ВЫПИСКА, ЗАКЛЮЧЕНИЕ, УВЕДОМЛЕНИЕ; or Казakh equivalents).
3) Canonical matching: fuzzy-match candidates to the Dictionary; normalize aliases and translations to the same canonical type.
4) Distinct detection: if two or more different canonical types are present, set single_doc_type=false.
5) Issuer check: only if two unrelated issuers each align to a different canonical type → single_doc_type=false.
6) Default safety: if ambiguous/noisy, prefer single_doc_type=true but keep detected_doc_types and set doc_type_known accordingly.

Output rules:
- Return exactly one valid JSON object; do not include code fences or extra text.
- Use double quotes for all JSON keys/values.

TEXT FOR ANALYSIS:
{}
"""

def check_single_doc_type(pages_obj: dict) -> str:
    pages_json_str = json.dumps(pages_obj, ensure_ascii=False)
    if not pages_json_str:
        return ""
    prompt = PROMPT.replace("{}", pages_json_str, 1)
    return ask_gpt(prompt)