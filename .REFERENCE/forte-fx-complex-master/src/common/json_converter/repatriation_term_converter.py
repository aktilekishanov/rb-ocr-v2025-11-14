import json
from typing import Dict, Any

from src.common.logger.logger_config import get_logger

logger = get_logger("repatriation_term_converter")

class RepatriationTermConverter:
    @staticmethod
    def _convert_days_to_term(days_str: str) -> str:
        """
        Convert days into repatriation term format: ddd.yy
        """
        try:
            days = int(days_str)
            if days < 180:
                raise ValueError("Minimum repatriation term is 180 days")
            if days > 9999:
                raise ValueError("Days value too large")

            years = days // 360
            leftover_days = days % 360
            return f"{leftover_days:03d}.{years:02d}"

        except (TypeError, ValueError):
            raise ValueError(f"Invalid repatriation term value: {days_str}")


    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process input dict and convert 'Срок репатриации' field value to format ddd.yy
        """
        for field in data.get("fields", []):
            if field.get("name") == "Срок репатриации":
                days = field.get("value")

                try:
                    field["value"] = self._convert_days_to_term(days)
                except ValueError:
                    logger.error( ValueError(f"Invalid repatriation term value: {days}") )

        return data


# Unit test
if __name__ == "__main__":

    rep = RepatriationTermConverter()
    data = json.loads('{"fields": [{"name": "Срок репатриации", "value": "1"}]}')
    print(data)
    print(rep.process(data))

