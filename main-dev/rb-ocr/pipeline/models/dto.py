"""
Lightweight DTO models used as typed contracts across the pipeline.
"""

from __future__ import annotations

try:
    from pydantic import BaseModel
except Exception:  # fallback to minimal BaseModel to avoid runtime crash if pydantic missing
    class BaseModel:  # type: ignore
        def __init__(self, **data):
            for k, v in data.items():
                setattr(self, k, v)

        @classmethod
        def model_validate(cls, data):  # type: ignore
            return cls(**data)

        def dict(self):  # type: ignore
            return self.__dict__

        def model_dump(self):  # type: ignore
            return self.__dict__


class DocTypeCheck(BaseModel):
    """
    Result of the LLM document-type classifier.
    """
    single_doc_type: bool | None = None
    confidence: float | None = None
    detected_doc_types: list[str] | None = None
    reasoning: str | None = None
    doc_type_known: bool | None = None


class ExtractorResult(BaseModel):
    """
    Result of the LLM data extractor for core fields.
    """
    fio: str | None = None
    doc_date: str | None = None


class OCRPage(BaseModel):
    """
    Single OCR page with page number and text content.
    """
    page_number: int
    text: str


class OCRPages(BaseModel):
    """
    Container for a list of OCR pages.
    """

    pages: list[OCRPage] | None = None
