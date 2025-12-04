system_prompt = """

"""

general_instructions1 = """

    Extract all the information from provided documents in the provided format. If the information does not exist, place null. Follow the orders strictly.

    -You are a helpful assistant from Kazakhstan that extracts information from the provided documents.
    -Only take into account the russian part of the provided document
    -ONLY RESPOND IN JSON FORMAT WITHOUT HEADERS OR FOOTERS
    -ONLY OUTPUT USING THIS FORMAT
    -ONLY ONE POSSIBLE JSON DOCUMENT IS POSSIBLE. ONE OUTPUT.
    -Fill fields with russian. 
    -replace « with "
    -[] brackets specify the output format.
    -Do not invent new information
    -Write country names in Russian and Fully if not specified otherwise.
    -ONLY WRITE SHORT FORMS LIKE : "OOO" вместо Общество с ограниченной ответственностью, "TOO" вместо товарищество с ограниченной ответсвтенностью, "ОАО" и так далее

    There will also be line indexes for each word. For each attribute you are asked to find, include the line indexes where you have found the information. There can be several line indexes per attribute. BUT NOT MORE THAN 10. Also, include the page number that is indicated above.

    Estimate your own confidence (your_confidence, from 0.0 to 0.99) using the following:
        0.99: Clear, exact match of attribute label and value
        0.8: High likelihood, small ambiguity
        0.5: Multiple candidates or loose match
        0.3: Format-based guess without keyword match
        0.1: Very uncertain or based on context only
        Calculate final confidence as
        final_confidence = ocr_confidence * (your_confidence ** 1.5)
        (OCR confidence is the average from all line indexes used)
        final confidence must never be greater than ocr confidence

    The format of OCR output is following:
    filename, page number:
    [index][confidence] text
    [index][confidence] text ...

"""

prompt_main_docs1 = general_instructions1 + """

    Extract the following information from the provided documents.

    - Валютный договор: [string] The unique code of the agreement. Usually in the top of the document. Can be a mix of numbers and characters. Can include the word: Контракт before Number, in that case append "Контракт". If no explicit number found - null. 
    - Тип договора: [string] Either "Импорт" or "Экспорт". If the client is from Kazakhstan and the seller is from abroad, its "Импорт", if the client is from abroad and seller is from Kazakhstan its "Экспорт".
    - Дата валютного договора: [YYYY-MM-DD]. The date that the agreement was made on. Usually in the headers/footers/beginning of the text.
    - Дата окончания договора: [YYYY-MM-DD]. The date that the agreement expires.
    - Наименование или ФИО контрагента: [string]. The name of the seller or buyer from abroad (everywhere except Kazakhstan). Write their country.
    - Страна контрагента: [string]. The country the buyer or seller from abroad is from. Cannot be Kazakhstan.
    - Клиент: [string]. Name of the buyer/seller that is from Kazakhstan. Also add country, БИН.
    - Вид суммы договора: [string]  Если не найдено, выбери "ориентировочная". 
    - Валюта договора: [string ISO4217] (если никакой валюты нет то пиши USD)
    *Приведи в международный формат ISO 4217 (например, Евро → EUR, Доллар США → USD, Рубль → RUB, Тенге → KZT).*
    *Приведи в международный формат ISO 4217 (например, Евро → EUR, Доллар США → USD, Рубль → RUB, Тенге → KZT).*
    - Срок репатриации: <значение>  (Если Срок меньше 180 дней, то установи его равным 180 дням. Формат всегда X дней или дата в формате гггг-ММ-ДД.)
    - Способ расчетов по договору: <значение> return string. Only one number.
    - Сумма договора: <значение>  (выбери максимальную сумму, если никакой суммы нет то напиши null)


    #### **Данные о валютном договоре**
    - **Валютный договор** (номер или идентификатор договора) – **верни только сам номер, без поясняющего текста**.
    - **Тип договора** (экспортный или импортный. РЕШАЙ ЭТО В КОНЦЕ).  
    Сначала НАЙДИ **РОЛИ СТОРОН** в договоре(например, "Покупатель", "Поставщик","Клиент") далее смотри в **РЕКВИЗИТЫ** чтобы понять кто из какой страны :
    * Экспорт – это когда резидент Казахстана ПЕРЕДАЁТ ИЛИ ПОСТАВЛЯЕТ нерезиденту Казахстана товары, имущественные права или оказывает ему услуги.
    * Импорт – это когда нерезидент Казахстана ПЕРЕДАЁТ ИЛИ ПОСТАВЛЯЕТ резиденту Казахстана товары, имущественные права или оказывает ему услуги.
        Важно: ориентируйся на того, кто оказывает услугу. Если Казахстанский участник выполняет работу для нерезидента, это экспорт, даже если речь идет об агентском договоре.
    - **Дата валютного договора** (это дата его подписания или вступления в силу, фиксирующая начало обязательств сторон. Всегда указывай в формате ГГГГ-ММ-ДД, если дата указана в будущем относительно текущего дня, ищи дальше другую дату)
    - **Дата окончания договора** (всегда указывай в формате ГГГГ-ММ-ДД). Если написано бессрочно, то напиши "бессрочно", Если не найдено напиши null.


    #### **Информация о контрагенте** 
    - **Наименование или ФИО контрагента** – **укажи его роль в договоре (например, "Покупатель", "Заказчик", "Арендатор"). Ищи только в ПРЕАМБУЛЕ или в РЕКВИЗИТАХ договора, исключая компании из Казахстана**. 
    - **Страна контрагента** (ищи страну контрагента только в ПРЕАМБУЛЕ или в РЕКВИЗИТАХ договора исключая Казахстан,  выводи только двухбуквенный код страны (например, Россия → RU, Германия → DE).  
    - Клиент: участник договора, являющийся резидентом РК, который получает товары, работы или услуги, либо, наоборот, оказывает их иностранному контрагенту. Укажи его наименование,  страну, БИН код.


    #### **Финансовая информация** 
    - **Вид суммы договора** (Если сумма указана в основном тексте договора и рядом встречаются слова "ориентировочная", "спецификация", "приложение", "инвойс", "invoice", либо сумма отсутствует, то это "ориентировочная". Если явно указано "сумма настоящего договора составляет" или "общая сумма" и т.д., то это "общая"). Не учитывай суммы в спецификациях и дополнительных документах, опирайся только на основной договор.
    - **Сумма договора**. (бери только основную сумму, удаляя пробелы и заменяя точки на запятые, если несколько сумм, бери самую большую или ту где написано итоговая сумма).
    - **Валюта договора**
    - **Срок репатриации** – найди срок который наиболее логично относится к сроку возврата выручки (репатриации).Если найденное максимальное значение меньше 180 дней, то установи его равным 180 дням
    - **Способ расчетов по договору** (Допустим выбор сразу нескольких способов)
        * 11 - платеж и (или) перевод денег в рамках аккредитива.
        * 12 - платеж и (или) перевод денег в рамках банковской гарантии.
        * 13 - предварительная оплата по экспорту (предварительная поставка по импорту).
        * 14 - оплата после отгрузки товара по экспорту (поставка после оплаты товара по импорту).
        Ищи в части где говорится про оплату в основном договоре. Обрати внимание на слова предоплата, оплата итд.
    
    
    Example of output:
    { "fields" : [
    {
      "name": "Валютный договор",
      "value": "Т170725",
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [1] }
          ]
        }
      ]
    },
    {
      "name": "Тип договора",
      "value": "Импорт",
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [1, 2] }
          ]
        }
      ]
    },
    {
      "name": "Дата валютного договора",
      "value": "2025-07-17",
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [5, 6, 3] }
          ]
        }
      ]
    },
    {
      "name": "Дата окончания договора",
      "value": "2025-12-31",
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [2] }
          ]
        }
      ]
    },
    {
      "name": "Наименование или ФИО контрагента",
      "value": "DRTECH Corporation, Продавец, KR",
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [90] }
          ]
        }
      ]
    },
    {
      "name": "Страна контрагента",
      "value": "KR",
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [102] }
          ]
        }
      ]
    },
    {
      "name": "Клиент",
      "value": "TOO «ТЕZ PHARM», KZ, БИН 201140032729",
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [5, 4] }
          ]
        }
      ]
    },
    {
      "name": "Вид суммы договора",
      "value": "общая",
      "confidence": 0.9,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [1] }
          ]
        }
      ]
    },
    {
      "name": "Сумма договора",
      "value": "18000,00",
      "confidence": 0.75,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [1] }
          ]
        }
      ]
    },
    {
      "name": "Валюта договора",
      "value": "USD",
      "confidence": 0.98,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [1] }
          ]
        }
      ]
    },
    {
      "name": "Срок репатриации",
      "value": "180 дней",
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [1] }
          ]
        }
      ]
    },
    {
      "name": "Способ расчетов по договору",
      "value": "13",
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [0, 12, 44] }
          ]
        }
      ]
    },
    ]
    }
"""



prompt_extra_docs1 = general_instructions1 + """
    Extract the following information from the provided documents

    - Третьи лица: участники из **"Наименование или ФИО контрагента"**, не являющиеся основными сторонами (Поставщик/Покупатель, Исполнитель/Заказчик), но указанные как получатели товаров, денег или посредники. Ищи только в преамбуле или реквизитах. Укажи их название, ИНН/УНП, страну и роль (например, "Гарант", "Фактор", "Получатель"). FORMAT AS STRING, not json  Если нет – null. BANKS ARE NOT THIRD PARTIES
    - Грузополучатель: – [string]. Find the name of the Грузополучатель. Грузополучатель is always written explicitly, search for the exact word. Also add ИНН and country
    - Грузоотправитель: – [string]. Find the name of the Грузоотправитель. Грузоотправитель is always written explicitly, search for the exact word. Also add ИНН and country
    - Производитель: – [string]. The company or other unit that made the goods that are being sold or bought. If the product names being sold, contain the name of the seller, then производитель is seller.If not found explicitly, null. 
    - Валюта платежа: <значение>. The currency in which the payment will be made. Do not confuse with agreement currency, only find the payment currency
    *Приведи в международный формат ISO 4217 (например, Евро → EUR, Доллар США → USD, Рубль → RUB, Тенге → KZT).*
    - Код вида валютного договора: <значение>
    - Категория товара: <максимальное значение>
    - БИК/SWIFT:<все значения и верни только сам БИК/SWIFT:> Return as list of strings .
    - ТНВЭД код:<все значения и верни только сам ТНВЭД код:> Return as list of strings, if not found, null. 
    - Наименование продукта - Наименование товаров/работ/услуг, ONLY IN RUSSIAN. Dont include information form specifications. Keep brief.
    - Пересечение РК: - <максимальное значение>, if there is no physical goods crossing KZ borders, null
    - Ссылки на документы: - return as list of strings. List the names of documents other than the main agreement document. Dont return URL's

    ### Извлеки следующую структурированную информацию:
    - Третьи лица: участники договора, не являющиеся основными сторонами (Поставщик/Покупатель, Исполнитель/Заказчик), но указанные как получатели товаров, денег или посредники. Укажи их название, БИН код, страну и роль (например, "Гарант", "Фактор", "Получатель"). Ищи только в преамбуле или реквизитах.
    - **Грузополучатель** – если в договоре указан грузополучатель, укажи его наименование или ФИО, БИН код, страну. Ищи только в преамбуле,приложении к договору или в реквизитах договора. Если не найден, укажи null.
    - **Грузоотправитель** – если в договоре указан грузоотправитель, укажи его наименование или ФИО, БИН код, страну. Ищи только в преамбуле,приложении к договору или в реквизитах договора. Если не найден, укажи null.
    - **Производитель** – если в договоре указан производитель (товара или услуги), укажи его наименование, БИН код, страну. Ищи только в преамбуле,приложении к договору или в реквизитах договора. Если не найден, укажи null.


    #### **Финансовая информация** 
    - **Валюта платежа - Только валюта в которой производится оплата. Ключевые слова: валюта платежа, оплата, платеж, расчет. Не бери валюту договора или контракта.
    - **Код вида валютного договора**:  
        * 1 - товар (если упоминаются поставки товаров).
        * 2 - услуга (если речь идет об услугах, например, консультационных, логистических, IT).
        * 3 - смешанный (если есть и товары, и услуги).
        * 4 - без перемещения товаров (если товар никуда не перемещается из страны в другую).
        * 5 - электронные деньги (если речь об электронных платежах).
    - **Категория товара** - если договор предусматривает поставку товара, определи его категорию (при наличии, верни только номер без текста). 
        * 0 – Прочее
        * 1 – Связан с нефтью и нефтепродуктами
        * 2 – Связан с автомобилями
        * 3 – Связан с электроникой
        * 4 – Связан с древесной продукцией

    - **БИК/SWIFT** - найди все БИК/SWIFT (ищи БИК/SWIFT только в реквизитах договора). Cannot be anything else than SWIFT CODE or null.  
    - **ТНВЭД код (HS code)** – если найден, укажи его, иначе "Не найдено".
    - **Наименование продуктов** - Наименование товаров/работ/услуг
    - **Пересечение РК** – Выведи **1**, если товар или услуга **пересекают границу Казахстана** (ищи слова типа "пересечение", "вывоз", "ввоз"). Если реализуется **за пределами** Казахстана без пересечения границы, выведи **0**. Если явных указаний нет, определяй по контексту
    - **Ссылки на документы** - Проверь договор на наличие ссылок на другие документы. Выведи названия этих документов, если они упоминаются
    
    Example of output:
    { "fields" : [

    {
      "name": "Третьи лица",
      "value": null,
      "confidence": 0.0,
      "references": []
    },
    {
      "name": "Грузополучатель",
      "value": "TOO «ТЕZ PHARM», 201140032729, KZ",
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [1] }
          ]
        }
      ]
    },
    {
      "name": "Грузоотправитель",
      "value": null,
      "confidence": 0.0,
      "references": []
    },
    {
      "name": "Производитель",
      "value": "DRTECH Corporation, null, KR",
      "confidence": 0.66,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [1] }
          ]
        }
      ]
    },
    {
      "name": "Валюта платежа",
      "value": "USD",
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [1] }
          ]
        }
      ]
    },
    {
      "name": "Код вида валютного договора",
      "value": "1",
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [1, 5, 6] }
          ]
        }
      ]
    },
    {
      "name": "Категория товара",
      "value": "0",
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [190] }
          ]
        }
      ]
    },
    {
      "name": "БИК/SWIFT",
      "value": [
        "KOEXKRSE",
        "IRTYKZKA",
        "RZBAATWW"
      ],
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [1] }
          ]
        }
      ]
    },
    {
      "name": "ТНВЭД код",
      "value": null,
      "confidence": 0.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [88] }
          ]
        }
      ]
    },
    {
      "name": "Наименование продукта",
      "value": [
        "Мобильная рентгенологическая система"
      ],
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [123] }
          ]
        }
      ]
    },
    {
      "name": "Пересечение РК",
      "value": "1",
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [91] }
          ]
        }
      ]
    },
    {
      "name": "Ссылки на документы",
      "value": [
        "Приложение №1",
        "Инвойс на русском"
      ],
      "confidence": 1.0,
      "references": [
        {
          "filename": "file.pdf",
          "occurrences": [
            { "page": 1, "index": [1] }
          ]
        }
      ]
    }
    ]
    }
"""

prompt_reasoning_fields = """

"""




