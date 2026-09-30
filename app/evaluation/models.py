from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.domain import NodeMetric, utc_now


RouterMode = Literal["fixed", "llm", "hybrid"]
OutputName = Literal[
    "jd_info",
    "company_info",
    "salary_info",
    "match_result",
    "final_report",
]


class EvaluationCase(BaseModel):
    """One router-independent benchmark case and its expected minimal behavior."""

    id: str
    category: Literal["company", "salary", "match", "comprehensive", "edge"]
    description: str
    request: dict[str, Any]
    expected_agents: list[str]
    required_outputs: list[OutputName]
    requires_sources: bool = False


class EvaluationRecord(BaseModel):
    """Result of running one case with one routing strategy."""

    run_id: str
    case_id: str
    router_mode: RouterMode
    model_backend: str
    search_backend: str
    status: str
    expected_agents: list[str]
    actual_route: list[str]
    route_precision: float = Field(ge=0, le=1)
    route_recall: float = Field(ge=0, le=1)
    exact_route_match: bool
    redundant_agents: list[str] = Field(default_factory=list)
    missing_agents: list[str] = Field(default_factory=list)
    task_success: bool
    missing_outputs: list[str] = Field(default_factory=list)
    source_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    total_latency_ms: int = Field(default=0, ge=0)
    token_usage: int = Field(default=0, ge=0)
    node_metrics: list[NodeMetric] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class EvaluationSummary(BaseModel):
    router_mode: RouterMode
    cases: int = Field(ge=0)
    task_success_rate: float = Field(ge=0, le=1)
    average_route_precision: float = Field(ge=0, le=1)
    average_route_recall: float = Field(ge=0, le=1)
    exact_route_match_rate: float = Field(ge=0, le=1)
    average_latency_ms: float = Field(ge=0)
    average_token_usage: float = Field(ge=0)
