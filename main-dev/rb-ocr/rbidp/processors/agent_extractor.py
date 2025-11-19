from rbidp.clients.gpt_client import ask_gpt
import json
 
PROMPT = """
You are an expert in multilingual document information extraction and normalization.
Your task is to analyze a noisy OCR text that may contain both Kazakh and Russian fragments.
 
Follow these steps precisely before producing the final JSON:
 
STEP 1 — UNDERSTAND THE TASK
You must extract the following information:
- fio: full name of the person (e.g. **Иванов Иван Иванович**)
- doc_date: main issuance date (convert to format DD.MM.YYYY)
 
STEP 2 — EXTRACTION RULES
- If several dates exist, choose the main issuance date (usually near header or "№").
- For decree documents (Приказ о выходе в декретный отпуск по уходу за ребенком; Справка о выходе в декретный отпуск по уходу за ребенком):
  - If the issuance date cannot be found, parse a period clause and set doc_date to the start date of that period.
  - Recognize RU variants: «с DD.MM.YYYY … по DD.MM.YYYY», «с DD.MM.YYYY … до DD.MM.YYYY».
  - Recognize KZ variants: «DD.MM.YYYY бастап … DD.MM.YYYY дейін».
- Ignore duplicates or minor typos.
- When the value is missing, set it strictly to `null`.
- Do not invent or assume missing data.
- If both Russian and Kazakh versions exist, output result in Russian.
- Always include surname, given name, and patronymic (if available).
- If the name appears in oblique case (e.g. Ивановой Марине Олеговне), convert it to nominative form (e.g. Иванова Марина Олеговна).
- If the text contains both a full and abbreviated form (e.g. "Аметовой М.М." and "Аметовой Мереке Маратовне"),
  **always select the full explicit version**.
 
NOTE:
- for "Справка об инвалидности" doc_date appears at the bottom of the document with format YY DD month-string (e.g. 18 30 январь → 30.01.2018)
 
STEP 3 — THINK BEFORE ANSWERING
Double-check:
- Is fio complete (Фамилия Имя Отчество)?
- Is doc_date formatted as DD.MM.YYYY?
- Are there exactly 2 keys in the final JSON?
 
STEP 4 — OUTPUT STRICTLY IN THIS JSON FORMAT (no explanations, no extra text, no Markdown formatting, and no ```json formatting)
{
  "fio": string | null,
  "doc_date": string | null
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
 
 
 