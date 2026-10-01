from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AnalysisHistoryItem(BaseModel):
    thread_id: str
    company_name: str
    job_title: str | None = None
    status: Literal["running", "completed", "failed"]
    match_score: int | None = Field(default=None, ge=0, le=100)
    recommendation: str | None = None
    created_at: datetime
    updated_at: datetime


class AnalysisHistoryResponse(BaseModel):
    items: list[AnalysisHistoryItem] = Field(default_factory=list)
