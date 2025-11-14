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
You are a **deterministic OCR document-type classifier**.
Your ONLY goal: analyze the given OCR text and decide whether it represents **one single document type** or **multiple distinct ones**.
Output **only** a single JSON object in this exact format:

{
  "single_doc_type": true | false,
  "detected_doc_types": [ "..." ],
  "reasoning": "..."
}
No extra text or commentary outside the JSON.
 
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
 
Fuzzy-match (Levenshtein ≥ 0.6) each candidate title to one of these canonical types:
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

**Important semantic aliases (normalize these as identical):**
* "о предоставлении отпуска по уходу за ребенком"
* "о выходе в декретный отпуск по уходу за ребенком"
* "о предоставлении декретного отпуска"

All refer to **one canonical type:**
**Приказ о выходе в декретный отпуск по уходу за ребенком.**
 
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
 
If uncertain, noisy, or ambiguous → default to
`{"single_doc_type": true, "detected_doc_types": [...], "reasoning": "Ambiguous or translated duplicates treated as one document type."}`
 
---
 
### 8. Output Rules

* Return **exactly one** valid JSON object.
* Do **not** include markdown formatting, code fences, or explanations.
* JSON keys and string values must be enclosed in double quotes.
 
---
 
### TEXT FOR ANALYSIS
{}
"""

def check_single_doc_type(pages_obj: dict) -> str:
    pages_json_str = json.dumps(pages_obj, ensure_ascii=False)
    if not pages_json_str:
        return ""
    prompt = PROMPT.replace("{}", pages_json_str, 1)
    return ask_gpt(prompt)