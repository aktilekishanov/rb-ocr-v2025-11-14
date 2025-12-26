"""
Lightweight DTO models used as typed contracts across the pipeline.
"""

from __future__ import annotations

from pydantic import BaseModel


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
