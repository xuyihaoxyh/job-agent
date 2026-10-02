from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.domain import (
    AnalysisSectionStatus,
    CompanyInfo,
    CostSummary,
    MatchResult,
    NodeMetric,
    PlanDecision,
    RouterDecision,
    SalaryInfo,
    Source,
)


class AnalyzeResponse(BaseModel):
    thread_id: str
    status: Literal["completed", "failed", "running"]
    router_mode: Literal["fixed", "llm", "hybrid"]
    analysis_targets: list[Literal["company", "salary", "match"]] = Field(
        default_factory=list
    )
    match_result: MatchResult | None = None
    company_info: CompanyInfo | None = None
    salary_info: SalaryInfo | None = None
    sources: list[Source] = Field(default_factory=list)
    route_history: list[str] = Field(default_factory=list)
    metrics: list[NodeMetric] = Field(default_factory=list)
    router_decisions: list[RouterDecision] = Field(default_factory=list)
    analysis_plan: PlanDecision | None = None
    step_count: int = 0
    elapsed_ms: int = Field(default=0, ge=0)
    final_report: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    section_statuses: dict[str, AnalysisSectionStatus] = Field(default_factory=dict)
    cost_summary: CostSummary


class ThreadStateResponse(BaseModel):
    thread_id: str
    status: str
    values: dict[str, Any]
    next_nodes: list[str] = Field(default_factory=list)
