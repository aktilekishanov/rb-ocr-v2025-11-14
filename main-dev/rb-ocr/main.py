from rbidp.clients.gpt_client import ask_gpt
 
def main():

    # # Textract (three-line caller)
    # # work pc path: "C:/Users/AIshanov/personal/ds/rb-ocr/ocr-local/ocr-local-main/data/Приказ о выходе в декретный отпуск/3. Приказ о выходе в декретный отпуск.pdf"
    # pdf_path = "C:/Users/AIshanov/personal/ds/rb-ocr/ocr-local/ocr-local-main/data/Приказ о выходе в декретный отпуск/3. Приказ о выходе в декретный отпуск.pdf"
    # text = ask_textract(pdf_path, output_dir="output", save_json=True, save_filtered_json=True)
    # print(text)
    
    # # GPT (three-line caller)
    # prompt = "when is christmas in the states?"
    # response = ask_gpt(prompt)
    # print(response)



    # TEST GPT
    PROMPT_1 = """
    You are a deterministic OCR document-type classifier.
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
    
    {{
      "text": "«SMART SOLUTION Товаришество с ограниченной\nPERSON AL» ( PT smart ответственностью\nПЕРСОНАЛ\n» «smarrsoLuTION\nІН шектеуді серіктестігі PERSONAL» (СМАРТ\n| СОЛЮШН ПЕРСОНАЛ)»\nПРИКАЗ\n2024 жылғы 01 қараша Ne 3481-ЛС\nАлматы қаласы город Алматы\nЕңбек шартын бұзу Туралы\nБҰЙЫРАМЫН:\n1. Сакарияева Наргиз Кайратовна, Лорсаль Казахстан - Lux бөлімінің Сұлулық\nжөніндегі кеңесші| 2024 жылғы 26 наурыз № 00343 еңбек шарты 2024 жылғы 01\n| қараша бастап Қазақстан Республикасы Еңбек кодексінің 49-б. 5) тт. сәйкес,\nқызметкердің бастамасы бойынша БҰЗЫЛСЫН.\n2. 2024 жылғы 26 наурыв бастап 2024 жылғы 01 қараша дейінгі жұмыс кезеңі үшін\n| күнтізбелік 8 (сөгіз) күн мөлшерінде пайдаланылмаған жыл сайынғы ақы\nтөленетін еңбек дамалысы өтемақы төленсін,\n01.11.2024 К. өтініші.\nВ. Мукуёва\nтаныстым: 7 jot\nСакарияева H.K 01.11.2024\n\n«SMART SOLUTION Товаришество с ограниченной\n| PERSONAL» (СМАРТ smart ответственностью\nСОЛЮШН ПЕРСОНАЛ)»\nІ » 6ОЮШШОП6\nжауапкершілігі шектеулі серіктестігі PERSONAL» (СМАРТ\n| || СОЛЮЩШН ПЕРСОНАЛ)»\nБҰЙРЫҚ | ПРИКАЗ\n01 ноября 2024 года Хо 3481-ЛС\nАлматы қаласы город Алматы\nО расторжении договора\nПРИКАЗЫВАЮ:\nРАСТОРГНУТЬ трудовой договор от 26 марта 2024 года Ne 00343 с\nСакарияевой Наргиз Кайратовной, Консультантом красоты отдела Лореаль\nКазахстан - Lux (1 ноября 2024 года в соответствии с пп. 5 ст. 49 Трудового\n‚ кодекса РК. Расторжение трудового договора по инициативе работника.\n2. Выплатить компефнсацию за неиспользованный оплачиваемый ежегодный\nтрудовой отпуск Ң количестве 8 (восемь) календарных дней за период работы с\n26 мар 2024 года па 01 ноября 2024 года.\nСакарияева Н;\n2\ntp the В. Мукубва\nС приказом ознакомлрн(а): (as\nСакарияева Н.К. 01.11.2024\n(подпись) /",
    }}
    """








    PROMPT_2 = """
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
    - for "Справка об инвалидности" doc_date appears at the bottom of the document with format YY DD month-string (e.g. 18 30 январь → 30.01.2018).
    - for "Заключение врачебно-консультативной комиссии (ВКК)" doc_date appears at after the text "Форма № 026/у Заключение врачебно — консультационной комиссии".
    
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
    {{
      "text": "«SMART SOLUTION Товаришество с ограниченной\nPERSON AL» ( PT smart ответственностью\nПЕРСОНАЛ\n» «smarrsoLuTION\nІН шектеуді серіктестігі PERSONAL» (СМАРТ\n| СОЛЮШН ПЕРСОНАЛ)»\nПРИКАЗ\n2024 жылғы 01 қараша Ne 3481-ЛС\nАлматы қаласы город Алматы\nЕңбек шартын бұзу Туралы\nБҰЙЫРАМЫН:\n1. Сакарияева Наргиз Кайратовна, Лорсаль Казахстан - Lux бөлімінің Сұлулық\nжөніндегі кеңесші| 2024 жылғы 26 наурыз № 00343 еңбек шарты 2024 жылғы 01\n| қараша бастап Қазақстан Республикасы Еңбек кодексінің 49-б. 5) тт. сәйкес,\nқызметкердің бастамасы бойынша БҰЗЫЛСЫН.\n2. 2024 жылғы 26 наурыв бастап 2024 жылғы 01 қараша дейінгі жұмыс кезеңі үшін\n| күнтізбелік 8 (сөгіз) күн мөлшерінде пайдаланылмаған жыл сайынғы ақы\nтөленетін еңбек дамалысы өтемақы төленсін,\n01.11.2024 К. өтініші.\nВ. Мукуёва\nтаныстым: 7 jot\nСакарияева H.K 01.11.2024\n\n«SMART SOLUTION Товаришество с ограниченной\n| PERSONAL» (СМАРТ smart ответственностью\nСОЛЮШН ПЕРСОНАЛ)»\nІ » 6ОЮШШОП6\nжауапкершілігі шектеулі серіктестігі PERSONAL» (СМАРТ\n| || СОЛЮЩШН ПЕРСОНАЛ)»\nБҰЙРЫҚ | ПРИКАЗ\n01 ноября 2024 года Хо 3481-ЛС\nАлматы қаласы город Алматы\nО расторжении договора\nПРИКАЗЫВАЮ:\nРАСТОРГНУТЬ трудовой договор от 26 марта 2024 года Ne 00343 с\nСакарияевой Наргиз Кайратовной, Консультантом красоты отдела Лореаль\nКазахстан - Lux (1 ноября 2024 года в соответствии с пп. 5 ст. 49 Трудового\n‚ кодекса РК. Расторжение трудового договора по инициативе работника.\n2. Выплатить компефнсацию за неиспользованный оплачиваемый ежегодный\nтрудовой отпуск Ң количестве 8 (восемь) календарных дней за период работы с\n26 мар 2024 года па 01 ноября 2024 года.\nСакарияева Н;\n2\ntp the В. Мукубва\nС приказом ознакомлрн(а): (as\nСакарияева Н.К. 01.11.2024\n(подпись) /",
    }}
    """



    response_1 = ask_gpt(PROMPT_1)
    print(response_1)
    print("\n\n")
    response_2 = ask_gpt(PROMPT_2)
    print(response_2)

 
if __name__ == "__main__":
    main()

 