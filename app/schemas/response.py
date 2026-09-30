from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.domain import CompanyInfo, MatchResult, NodeMetric, SalaryInfo, Source


class AnalyzeResponse(BaseModel):
    thread_id: str
    status: Literal["completed", "failed", "running"]
    match_result: MatchResult | None = None
    company_info: CompanyInfo | None = None
    salary_info: SalaryInfo | None = None
    sources: list[Source] = Field(default_factory=list)
    route_history: list[str] = Field(default_factory=list)
    metrics: list[NodeMetric] = Field(default_factory=list)
    step_count: int = 0
    elapsed_ms: int = Field(default=0, ge=0)
    final_report: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)


class ThreadStateResponse(BaseModel):
    thread_id: str
    status: str
    values: dict[str, Any]
    next_nodes: list[str] = Field(default_factory=list)
