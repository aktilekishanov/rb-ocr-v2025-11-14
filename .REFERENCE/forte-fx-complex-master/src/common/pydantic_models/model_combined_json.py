import re
from datetime import date
from enum import Enum
from typing import Optional, Union, Any

from pydantic import BaseModel, field_validator, Field
from pydantic import ValidationInfo

from src.common.logger.logger_config import get_logger

logger = get_logger("pydantic_model_with_index")


class Occurrence(BaseModel):
    page: int
    index: list[int]


class Reference(BaseModel):
    confidence: float
    filename: str
    occurrences: list[Occurrence]


class Names(Reference):
    value: Optional[str]


class RepatriationTerm(Reference):
    value: Optional[int]


class Entity(BaseModel):
    names: str
    country: str
    id_name: Optional[str]
    id_value: Optional[str]

    def __str__(self) -> str:
        parts = [self.names, self.country]
        if self.id_name and self.id_value:
            parts.append(f"{self.id_name}" + " " + f"{self.id_value}")
        return ', '.join(parts)


class EntityType(Entity):
    role: str

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base}, {self.role}"


class AdditionalParties(Reference):
    value: Optional[list[EntityType]]

    def __str__(self) -> str:
        if self.value:
            return ', '.join([str(entity) for entity in self.value])
        else:
            return None


class Consignee(Reference):
    value: Optional[Entity]

    def __str__(self) -> str:
        if self.value is not None:
            return str(self.value)
        else:
            raise ValueError(f"{self.value} should be convertible to string")


class Consignor(Reference):
    value: Optional[Entity]

    def __str__(self) -> str:
        if self.value is not None:
            return str(self.value)
        else:
            raise ValueError(f"{self.value} should be convertible to string")


class ProductManufacturer(Reference):
    value: Optional[Entity]

    def __str__(self) -> str:
        if self.value is not None:
            return str(self.value)
        else:
            raise ValueError(f"{self.value} should be convertible to string")


class ProductCategoryEnum(int, Enum):
    OIL_AND_PETROLEUM = 1  # Связан с нефтью и нефтепродуктами
    AUTOMOBILES = 2  # Связан с автомобилями
    ELECTRONICS = 3  # Связан с электроникой
    WOOD_PRODUCTS = 4  # Связан с древесной продукцией
    OTHER = 0  # Прочее


class ProductCategory(Reference):
    value: Optional[ProductCategoryEnum]


class BicSwift(Reference):
    value: Optional[list[str]]


class HsCode(Reference):
    value: Optional[list[str]]


class SubjectName(Reference):
    value: Optional[str]


class DocumentReferences(Reference):
    value: Optional[list[str]]


class Amount(Reference):
    value: Optional[float]


class BankName(Reference):
    value: Optional[str]


class Route(Reference):
    value: Optional[str]


class ContractID(Reference):
    value: Optional[str]


class TradeTypeEnum(str, Enum):
    EXPORT = "экспорт"
    IMPORT = "импорт"


class TradeType(Reference):
    value: TradeTypeEnum


class Response(BaseModel):
    is_purchasing: bool
    reasoning: str


class ContractDate(Reference):
    value: Optional[date]


class PartyName(Reference):
    value: Optional[str]


class ForeignPartyCountry(Reference):
    value: Optional[str]


class AmountTypeEnum(str, Enum):
    general = "общая"
    approximate = "ориентировочная"


class AmountType(Reference):
    value: Optional[AmountTypeEnum]


class ContractSummary(Reference):
    value: Optional[str]


class Currency(Reference):
    value: Optional[str] = "USD"


class PaymentCurrency(Reference):
    value: Optional[list[str]]

    def __str__(self) -> str:
        if self.value:
            return ', '.join(self.value)
        else:
            raise ValueError(f"{self.value} should be convertible to string")


class ParsingResults(BaseModel):
    contract_id: ContractID
    trade_type: TradeType
    contract_start_date: ContractDate
    contract_end_date: ContractDate
    foreign_party_name: PartyName
    foreign_party_country: ForeignPartyCountry
    kazakhstan_party_name: PartyName
    amount_type: AmountType
    contract_currency: Currency
    contract_summary: ContractSummary
    contract_amount: Amount
    additional_parties: AdditionalParties
    consignee: Consignee
    consignor: Consignor
    product_manufacturer: Optional[ProductManufacturer]
    payment_currency: PaymentCurrency
    product_category_code: ProductCategory
    bic_swift: BicSwift
    hs_code: HsCode
    subject_name: SubjectName
    document_references: DocumentReferences
    counterparty_bank_name: BankName
    correspondent_bank_name: BankName
    names: Names
    route: Optional[Route]


class PaymentMethodEnum(int, Enum):
    PREPAYMENT = 13
    POSTPAYMENT = 14


## Reasoning

class ContractTypeCodeEnum(int, Enum):
    GOODS_CROSS_BORDER = 1  # Товар с пересечением границы
    SERVICES = 2  # Услуги
    GOODS_AND_SERVICES = 3  # Товары и услуги
    GOODS_NO_BORDER = 4  # Товар без пересечения границы
    ELECTRONIC_PAYMENTS = 5  # Электронные платежи


class BorderCrossingEnum(int, Enum):
    CROSSES = 1  # Пересекает границу РК
    NO_CROSSING = 0  # Не пересекает границу


class PaymentMethod(Reference):
    """Способ расчетов по договору"""
    value: Optional[list[PaymentMethodEnum]]

    def __str__(self) -> str:
        if self.value:
            return ', '.join([str(v.value) for v in self.value])
        else:
            raise ValueError(f"{self.value} should be convertible to string")


class ContractTypeCode(Reference):
    """Код вида валютного договора"""
    value: ContractTypeCodeEnum


class BorderCrossing(Reference):
    """Пересечение границы РК"""
    value: BorderCrossingEnum


# Main Result Model
class ParsingResultsReasoning(BaseModel):
    repatriation_term: RepatriationTerm
    payment_method: PaymentMethod
    contract_type_code: ContractTypeCode
    border_crossing: BorderCrossing


class IndependentFields(BaseModel):
    contract_id: ContractID  # 'Валютный договор'
    contract_start_date: ContractDate  # 'Дата валютного договора'
    contract_end_date: ContractDate  # 'Дата окончания договора'
    foreign_party_country: ForeignPartyCountry  # 'Страна контрагента'
    amount_type: AmountType  # 'Вид суммы договора'
    contract_currency: Currency  # 'Валюта договора'
    contract_summary: ContractSummary  # 'Описание договора'
    contract_amount: Amount  # 'Сумма договора'
    additional_parties: AdditionalParties  # 'Третьи лица'
    consignee: Consignee  # 'Грузополучатель'
    consignor: Consignor  # 'Грузоотправитель'
    product_manufacturer: Optional[ProductManufacturer]  # 'Производитель'
    payment_currency: PaymentCurrency  # 'Валюта платежа'
    product_category_code: ProductCategory  # 'Категория товара'
    bic_swift: BicSwift  # 'БИК/SWIFT'
    hs_code: HsCode  # 'ТНВЭД код'
    subject_name: SubjectName  # 'Наименование продукта'
    document_references: DocumentReferences  # 'Ссылки на документы'
    counterparty_bank_name: BankName  # 'Наименование банка контрагента'
    correspondent_bank_name: BankName  # 'Наименование банка корреспондента'
    names: Names  # 'ФИО'
    route: Optional[Route]  # 'Маршрут'
    contract_type_code: ContractTypeCode  # 'Код вида валютного договора'


class TradeClientFields(BaseModel):
    trade_type: TradeType
    kazakhstan_party_name: PartyName


class DependentFields(BaseModel):
    foreign_party_name: PartyName
    repatriation_term: RepatriationTerm
    payment_method: PaymentMethod
    border_crossing: BorderCrossing


class CombinedResult(IndependentFields, DependentFields, TradeClientFields):
    pass


class IndexReference(BaseModel):
    filename: str
    occurrences: list[Occurrence]


class IndexedFieldItem(BaseModel):
    name: str
    value: Optional[Any] = None
    confidence: Optional[float] = None
    references: Optional[list[IndexReference]] = None

    @field_validator("value", mode="after")
    @classmethod
    def enforce_min_repatriation_term(cls, v, info: ValidationInfo):
        """
        Ensure REPATRIATION_TERM is at least 180.
        Works for int or List[int]. If value < 180 => 180.
        """
        name = (info.data or {}).get("name")
        if name != "Срок репатриации" or v is None:
            return v

        def normalize_one(val) -> int:
            if not isinstance(val, int):
                logger.warning(f"Expected int, got {type(val).__name__}, defaulting to 180")
                return 180
            if val < 180:
                logger.warning(f"REPATRIATION_TERM {val} < 180, enforcing minimum")
                return 180
            return val

        if isinstance(v, list):
            return [normalize_one(item) for item in v]
        if isinstance(v, int):
            return normalize_one(v)
        return v


class CombinedExtractionModel(BaseModel):
    fields: list[IndexedFieldItem]


class FbData(BaseModel):
    EMAIL: str = ""
    PHONE: str = ""
    AMOUNT: str = ""
    CLIENT: str = ""
    ADDRESS: str = ""
    CHANNEL: str = ""
    TAX_CODE: str = ""
    DOCUMENT_ID: str = ""
    CONTRACT_DATE: str = ""
    CONTRACT_TYPE: str = ""
    AML_RISK_LEVEL: str = ""
    OPERATION_TYPE: str = ""
    PAYMENT_CURRENCY: str = ""
    CONTRACT_CURRENCY: str = ""
    CONTRACT_END_DATE: str = ""
    COUNTERPARTY_NAME: str = ""
    REPATRIATION_TERM: str = ""
    CONTRACT_AMOUNT_TYPE: str = ""
    COUNTERPARTY_COUNTRY: str = ""
    CURRENCY_CONTRACT_NUMBER: str = ""
    CURRENCY_CONTRACT_TYPE_CODE: str = ""

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "FbData":

        if not data:
            return cls()

        normalized: dict[str, str] = {}
        for field_name in cls.model_fields.keys():
            raw_val = data.get(field_name)
            if raw_val is None:
                normalized[field_name] = ""
            else:
                normalized[field_name] = str(raw_val)

        return cls(**normalized)

    def as_dict(self) -> dict[str, str]:
        dumped = self.model_dump()
        return {k: ("" if v is None else str(v)) for k, v in dumped.items()}
