from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class FileInfo(BaseModel):
    Truename: str
    Document: str


class FilesOnlyResponse(BaseModel):
    DocumentBasic: list[FileInfo]
    ApplicationDocument: list[FileInfo]


class Occurrence(BaseModel):
    page: int
    bbox: list[int]


class Reference(BaseModel):
    filename: str
    occurrences: list[Occurrence]


class FieldCoordinates(BaseModel):
    name: str
    value: str | list[str] | None = None
    name_eng: str | None = None
    confidence: float | None = None
    references: list[Reference]


class CoordinatesResponse(BaseModel):
    fields: list[FieldCoordinates]


class StatusResponse(BaseModel):
    status: str | None


class ResultResponse(BaseModel):
    result: Any | None


class Attribute(BaseModel):
    AttributeName: str
    Value: str


class DocumentContent(BaseModel):
    document_id: str = Field(..., alias="Document_id")
    data: list[Attribute] = Field(..., alias="Data")
    document_basic: list[FileInfo] = Field(..., alias="DocumentBasic")
    application_document: list[FileInfo] = Field(..., alias="ApplicationDocument")

    model_config = ConfigDict(validate_by_name=True)


class DocumentPayload(BaseModel):
    document: DocumentContent = Field(..., alias="Document")

    model_config = ConfigDict(validate_by_name=True)


class CorrectionCreate(BaseModel):
    field_name: str
    correct_value: Any | None = None


class CorrectionResponse(BaseModel):
    document_id: str
    field_name: str
    current_value: Any | None
    correct_value: Any

    model_config = ConfigDict(from_attributes=True)
