from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.domain import NodeMetric, utc_now

RouterMode = Literal["fixed", "llm", "hybrid"]
AssertionOperator = Literal[
    "equals",
    "contains",
    "not_contains",
    "contains_all",
    "between",
    "is_empty",
    "not_empty",
]
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
    forbidden_agents: list[str] = Field(default_factory=list)
    required_outputs: list[OutputName]
    requires_sources: bool = False
    required_source_outputs: list[Literal["company_info", "salary_info"]] = Field(
        default_factory=list
    )
    assertions: list["EvaluationAssertion"] = Field(default_factory=list)


class EvaluationAssertion(BaseModel):
    """One deterministic assertion against a dotted path in the graph result."""

    path: str
    operator: AssertionOperator
    expected: Any = None


class AssertionResult(BaseModel):
    path: str
    operator: AssertionOperator
    expected: Any = None
    actual: Any = None
    passed: bool


class EvaluationRecord(BaseModel):
    """Result of running one case with one routing strategy."""

    run_id: str
    case_id: str
    repeat_index: int = Field(default=1, ge=1)
    router_mode: RouterMode
    model_backend: str
    model_name: str = "unknown"
    prompt_version: str = "v1"
    search_backend: str
    status: str
    expected_agents: list[str]
    actual_route: list[str]
    route_precision: float = Field(ge=0, le=1)
    route_recall: float = Field(ge=0, le=1)
    route_f1: float = Field(ge=0, le=1)
    exact_route_match: bool
    redundant_agents: list[str] = Field(default_factory=list)
    missing_agents: list[str] = Field(default_factory=list)
    forbidden_agents: list[str] = Field(default_factory=list)
    task_success: bool
    missing_outputs: list[str] = Field(default_factory=list)
    missing_source_outputs: list[str] = Field(default_factory=list)
    repeated_agents: list[str] = Field(default_factory=list)
    forbidden_agents_hit: list[str] = Field(default_factory=list)
    assertion_results: list[AssertionResult] = Field(default_factory=list)
    assertion_accuracy: float | None = Field(default=None, ge=0, le=1)
    grounded_claim_rate: float | None = Field(default=None, ge=0, le=1)
    source_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    total_latency_ms: int = Field(default=0, ge=0)
    token_usage: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0, ge=0)
    node_metrics: list[NodeMetric] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class EvaluationSummary(BaseModel):
    router_mode: RouterMode
    cases: int = Field(ge=0)
    task_success_rate: float = Field(ge=0, le=1)
    average_route_precision: float = Field(ge=0, le=1)
    average_route_recall: float = Field(ge=0, le=1)
    average_route_f1: float = Field(ge=0, le=1)
    exact_route_match_rate: float = Field(ge=0, le=1)
    forbidden_agent_violation_rate: float = Field(ge=0, le=1)
    assertion_accuracy: float | None = Field(default=None, ge=0, le=1)
    average_grounded_claim_rate: float | None = Field(default=None, ge=0, le=1)
    error_free_rate: float = Field(ge=0, le=1)
    average_latency_ms: float = Field(ge=0)
    p50_latency_ms: float = Field(ge=0)
    p95_latency_ms: float = Field(ge=0)
    average_token_usage: float = Field(ge=0)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    total_model_calls: int = Field(ge=0)
    total_estimated_cost_usd: float = Field(ge=0)
