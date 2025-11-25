from __future__ import annotations

from pydantic import BaseModel
from typing import Optional, Literal


class ErrorItem(BaseModel):
    code: str
    message: Optional[str] = None


class ProcessResponse(BaseModel):
    run_id: str
    verdict: bool
    errors: list[str]


class ProcessRequestMeta(BaseModel):
    fio: str


# Phase 2: async jobs
JobStatus = Literal["accepted", "running", "completed", "failed"]


class JobSubmitResponse(BaseModel):
    run_id: str
    status: Literal["accepted"]


class JobStatusResponse(BaseModel):
    run_id: str
    status: JobStatus
    verdict: bool | None = None
    errors: list[str] | None = None
