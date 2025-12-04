from typing import Dict, Union, Any

from src.common.pydantic_models.model_final_json import FieldName


class FBConverter:
    def __init__(self):
        # Create reverse mapping: Russian → Enum name
        self.translation_map = {v.value: v.name for v in FieldName}

    def flatten_and_translate(
        self, data: Dict[str, Any]
    ) -> Dict[str, Union[str, None]]:
        """
        Flatten 'fields' list into {EnglishName: value} dict.
        Lists in 'value' are joined with commas.
        """
        result = {}
        for field in data.get("fields", []):
            ru_name = field.get("name")
            value = field.get("value")
            if isinstance(value, list):
                value = ", ".join(map(str, value))
            elif value is None:
                value = None

            en_name = self.translation_map.get(ru_name, ru_name)  # fallback to original if not in map
            result[en_name] = value
        return result