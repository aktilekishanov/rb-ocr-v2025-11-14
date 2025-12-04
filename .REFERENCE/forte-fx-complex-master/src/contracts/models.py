from sqlalchemy import Column, Integer, String, DateTime, Text, func, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB

from src.core.database import Base


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(String, nullable=False, unique=True)
    status = Column(String, default="uploaded")
    data_json = Column(JSONB, nullable=True)
    docs_json = Column(JSONB, nullable=False)
    result_json = Column(JSONB, nullable=True)
    flat_result_json = Column(JSONB, nullable=True)
    cross_check_json = Column(JSONB, nullable=True)
    compliance_check_json = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class FieldCorrection(Base):
    __tablename__ = "field_corrections"

    document_id = Column(String, ForeignKey("contracts.document_id", ondelete="CASCADE"), primary_key=True,
                         nullable=False)
    field_name = Column(String, primary_key=True, nullable=False)
    current_value = Column(JSONB, nullable=True)
    correct_value = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), primary_key=True, nullable=False)
