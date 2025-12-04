from enum import Enum
from typing import List, Optional, Any

from pydantic import BaseModel, field_validator

from src.common.logger.logger_config import get_logger

logger = get_logger("pydantic_model_final_bbox")


class FieldName(str, Enum):
    BIK_SWIFT = "БИК/SWIFT"
    CONTRACT_CURRENCY = "Валюта договора"
    PAYMENT_CURRENCY = "Валюта платежа"
    CURRENCY_CONTRACT_NUMBER = "Валютный договор"
    CONTRACT_AMOUNT_TYPE = "Вид суммы договора"
    CONSIGNOR = "Грузоотправитель"
    CONSIGNEE = "Грузополучатель"
    CONTRACT_DATE = "Дата валютного договора"
    CONTRACT_END_DATE = "Дата окончания договора"
    PRODUCT_CATEGORY = "Категория товара"
    CLIENT = "Клиент"
    CURRENCY_CONTRACT_TYPE_CODE = "Код вида валютного договора"
    COUNTERPARTY_NAME = "Наименование или ФИО контрагента"
    PRODUCT_NAME = "Наименование продукта"
    CROSS_BORDER = "Пересечение РК"
    MANUFACTURER = "Производитель"
    PAYMENT_METHOD = "Способ расчетов по договору"
    REPATRIATION_TERM = "Срок репатриации"
    DOCUMENT_REFERENCES = "Ссылки на документы"
    COUNTERPARTY_COUNTRY = "Страна контрагента"
    AMOUNT = "Сумма договора"
    HS_CODE = "ТНВЭД код"
    CONTRACT_TYPE = "Тип договора"
    THIRD_PARTIES = "Третьи лица"
    CONTRACT_DESCRIPTION = "Описание договора"
    CONTRACT_NAMES = "ФИО"
    ROUTE = "Маршрут"
    CORRESPONDENT_BANK_NAME = "Наименование банка корреспондента"
    COUNTERPARTY_BANK_NAME = "Наименование банка контрагента"
    UN_CODE = "Присвоение УН"
    CONTRACT_TYPE_SYSTEM = "Тип договора для учетной системы"


ALLOWED_FIELD_NAMES = {item.value for item in FieldName}


class Occurrence(BaseModel):
    page: int
    bbox: List[int]


class Reference(BaseModel):
    filename: str
    occurrences: List[Occurrence]


class FieldItem(BaseModel):
    name: str
    value: Optional[Any] = None
    confidence: Optional[float] = None
    references: Optional[List[Reference]] = None

    # Normalize `value` before checking Union[str, List[str]]
    @field_validator("value", mode="before")
    @classmethod
    def normalize_value(cls, v: Any):
        if v is None:
            return None

        # Convert numbers/booleans to string
        if isinstance(v, (int, float, bool)):
            return str(v)

        # Strings: strip, convert empty to None
        if isinstance(v, str):
            v = v.strip()
            return v or None

        # Lists: flatten, remove None/empty, convert to string
        if isinstance(v, list):
            flat: List[str] = []

            def add_item(item):
                if item is None:
                    return
                if isinstance(item, list):
                    for sub in item:
                        add_item(sub)
                else:
                    s = str(item).strip()
                    if s:
                        flat.append(s)

            for item in v:
                add_item(item)

            if not flat:
                return None
            if len(flat) == 1:
                return flat[0]
            return flat

        # Everything else → string
        try:
            s = str(v).strip()
            return s or None
        except Exception:
            return None


class ContractExtractionResult(BaseModel):
    fields: List[FieldItem]

    # Filter before creating FieldItem models
    @field_validator("fields", mode="before")
    @classmethod
    def filter_and_validate_fields(cls, items):
        if not isinstance(items, list):
            return items

        # items are still raw dicts here
        input_names = {it.get("name") for it in items if isinstance(it, dict)}
        expected_names = ALLOWED_FIELD_NAMES

        missing = expected_names - {n for n in input_names if n}
        extra = {n for n in input_names if n} - expected_names

        if missing:
            logger.warning(f"Missing fields: {sorted(missing)}")
        else:
            logger.info("Validation successful, all expected fields are present.")

        if extra:
            logger.warning(f"Ignoring extra fields: {sorted(extra)}")

        # Keep only allowed fields

        return [it for it in items if isinstance(it, dict) and it.get("name") in expected_names]
