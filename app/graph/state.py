from __future__ import annotations

import operator
from typing import Annotated, Literal

from typing_extensions import TypedDict

from app.schemas.domain import (
    CompanyInfo,
    JDInfo,
    MatchResult,
    NodeError,
    NodeMetric,
    RouteEvent,
    SalaryInfo,
    Source,
    UserProfile,
)


class JobAnalysisState(TypedDict, total=False):
    user_id: str
    question: str
    jd_text: str
    company_name: str
    user_profile: UserProfile
    target_location: str | None
    currency: str
    router_mode: Literal["fixed"]

    jd_info: JDInfo
    company_info: CompanyInfo
    salary_info: SalaryInfo
    match_result: MatchResult

    completed_agents: Annotated[list[str], operator.add]
    route_events: Annotated[list[RouteEvent], operator.add]
    errors: Annotated[list[NodeError], operator.add]
    sources: Annotated[list[Source], operator.add]
    metrics: Annotated[list[NodeMetric], operator.add]
    step_count: Annotated[int, operator.add]

    final_report: str
    status: Literal["running", "completed", "failed"]

