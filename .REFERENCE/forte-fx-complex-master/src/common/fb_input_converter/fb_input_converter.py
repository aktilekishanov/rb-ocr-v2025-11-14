import json

class DocumentConverter:
    # === Mapping from input AttributeName → target output key ===
    ATTRIBUTE_MAP = {
        "БИК": "BIK_SWIFT",
        "END_DATE": "CONTRACT_END_DATE",
    }

    # === Final schema (your target attributes) ===
    OUTPUT_TEMPLATE = {
        "BIK_SWIFT": None,
        "CONTRACT_CURRENCY": None,
        "PAYMENT_CURRENCY": None,
        "CURRENCY_CONTRACT_NUMBER": None,
        "CONTRACT_AMOUNT_TYPE": None,
        "CONSIGNOR": None,
        "CONSIGNEE": None,
        "CONTRACT_DATE": None,
        "CONTRACT_END_DATE": None,
        "PRODUCT_CATEGORY": None,
        "CLIENT": None,
        "CURRENCY_CONTRACT_TYPE_CODE": None,
        "COUNTERPARTY_NAME": None,
        "PRODUCT_NAME": None,
        "CROSS_BORDER": None,
        "MANUFACTURER": None,
        "PAYMENT_METHOD": None,
        "REPATRIATION_TERM": None,
        "DOCUMENT_REFERENCES": None,
        "COUNTERPARTY_COUNTRY": None,
        "AMOUNT": None,
        "HS_CODE": None,
        "CONTRACT_TYPE": None,
        "THIRD_PARTIES": None,
        "UN_CODE": None,
        "CONTRACT_TYPE_SYSTEM": None,
    }

    @classmethod
    def convert(cls, input_json: dict) -> dict:
        """
        Convert input document JSON to flat target format.
        """
        output = cls.OUTPUT_TEMPLATE.copy()

        for attr in input_json.get("Document", {}).get("Data", []):
            name = attr.get("AttributeName")
            value = attr.get("Value")

            # If in mapping, use mapped key
            if name in cls.ATTRIBUTE_MAP:
                target_key = cls.ATTRIBUTE_MAP[name]
            else:
                # Otherwise keep same name if present in OUTPUT_TEMPLATE
                target_key = name if name in cls.OUTPUT_TEMPLATE else None

            if target_key:
                output[target_key] = value

        return output


if __name__ == "__main__":
    input_json = {
        "Document": {
            "Document_id": "1212121212",
            "Data": [
                {"AttributeName": "БИК", "Value": "160440005998"},
                {"AttributeName": "AML_RISK_LEVEL", "Value": "0"},
                {"AttributeName": "CURRENCY_CONTRACT_NUMBER", "Value": "DSD-5223"},
                {"AttributeName": "CONTRACT_DATE", "Value": "30.07.2025"},
                {"AttributeName": "END_DATE", "Value": "31.07.2025"},
                {"AttributeName": "OPERATION_TYPE", "Value": "Присвоение учетного номера по валютному договору"},
                {"AttributeName": "COUNTERPARTY_NAME", "Value": "АРАВ счсч Арв"},
                {"AttributeName": "CONTRACT_TYPE", "Value": "Экспорт"},
                {"AttributeName": "CONTRACT_CURRENCY", "Value": "USD"},
                {"AttributeName": "PAYMENT_CURRENCY", "Value": "EUR,KZT"},
                {"AttributeName": "EMAIL", "Value": "test@gmail.com"},
                {"AttributeName": "PHONE", "Value": "+77772522266"},
                {"AttributeName": "ADDRESS", "Value": "050022, КАЗАХСТАН, АЛМАТЫ г, БОСТАНДЫКСКИЙ р-н, САТПАЕВА ул, дом 9Б"},
                {"AttributeName": "CHANNEL", "Value": "IB"},
                {"AttributeName": "AMOUNT", "Value": "10000.00"}
            ]
        }
    }

    converter = DocumentConverter()
    result = converter.convert(input_json)
    print(json.dumps(result, ensure_ascii=False, indent=2))
