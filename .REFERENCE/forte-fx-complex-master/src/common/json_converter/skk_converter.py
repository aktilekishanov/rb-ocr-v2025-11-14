from typing import Any, Dict, List, Union, Optional


class SKKConverter:
    # Keep only these fields
    ALLOWED_NAME_ENG = {
        "CLIENT",
        "COUNTERPARTY_NAME",
        "COUNTERPARTY_BANK_NAME",
        "CORRESPONDENT_BANK_NAME",
        "CONSIGNOR",
        "CONSIGNEE",
        "MANUFACTURER",
        "THIRD_PARTIES",
        "CONTRACT_NAMES",
        "BIK_SWIFT",
        "CROSS_BORDER",
        "ROUTE",
        "HS_CODE"
    }

    @staticmethod
    def _to_str_or_none(x: Optional[Union[str, float, int]]) -> Optional[str]:
        if x is None:
            return None
        return str(x)

    def convert(self, data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Input format:
        {
          "fields": [
            {
              "name": "БИК/SWIFT",
              "value": [... or str],
              "confidence": 0.93,
              "references": [...],
              "name_eng": "BIK_SWIFT"
            },
            ...
          ]
        }

        Output format:
        {
          "fields": [
            { "name": <ru>, "name_eng": <eng>, "value": <str|list|None>, "confidence": <str|None> },
            ...
          ]
        }
        """
        result_fields: List[Dict[str, Any]] = []

        for f in data.get("fields", []):
            name_eng = f.get("name_eng")
            if not name_eng or name_eng not in self.ALLOWED_NAME_ENG:
                continue  # skip anything not in the whitelist

            result_fields.append(
                {
                    "name": f.get("name"),
                    "name_eng": name_eng,
                    "value": f.get("value"),  # keep lists as lists; keep scalars as-is; keep None
                    "confidence": self._to_str_or_none(f.get("confidence")),
                }
            )

        return {"fields": result_fields}
