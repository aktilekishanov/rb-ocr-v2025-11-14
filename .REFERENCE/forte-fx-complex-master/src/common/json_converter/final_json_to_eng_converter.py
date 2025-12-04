from copy import deepcopy

from src.common.pydantic_models.model_final_json import ContractExtractionResult, FieldName


class ContractExtractionConverter:
    @staticmethod
    def to_english_dict(model: ContractExtractionResult) -> dict:
        result = {"fields": []}

        for field in model.fields:
            try:
                enum_key = FieldName(field.name)
                english_key = enum_key.name.lower()
            except ValueError:
                continue  # Skip unknown or invalid field names

            field_dict = field.model_dump()
            field_dict["name"] = english_key  # Replace only the name with English
            result["fields"].append(field_dict)

        return result

    @staticmethod
    def to_eng_bbox_final(data: dict) -> dict:
        """
        Input: bbox-final dict with schema:
        {"fields": [{"name": "<RU>", "value": ..., "confidence": ..., "references": [...]}, ...]}

        Output: same structure, but each field gets an added "name_eng" (snake_case English key).
        Unknown/unsupported names get name_eng=None.
        """
        if not isinstance(data, dict) or "fields" not in data:
            raise ValueError("Expected dict with top-level 'fields' list")

        result = {"fields": []}
        for field in data.get("fields", []):
            name_ru = field.get("name")
            try:
                enum_key = FieldName(name_ru)
                name_eng = enum_key.name.upper()
            except ValueError:
                name_eng = None  # fallback for unmapped names

            new_field = deepcopy(field)
            new_field["name_eng"] = name_eng
            result["fields"].append(new_field)

        return result
