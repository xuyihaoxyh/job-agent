from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.domain import UserProfile


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jd_text: str = Field(min_length=20)
    company_name: str = Field(min_length=1)
    job_title: str | None = None
    employment_type: Literal["social", "campus", "intern"] = "social"
    question: str = "分析岗位匹配度、公司情况和预计薪资"
    analysis_targets: list[Literal["company", "salary", "match"]] = Field(
        default_factory=lambda: ["company", "salary", "match"], min_length=1
    )
    target_location: str | None = None
    currency: str = "CNY"
    router_mode: Literal["fixed", "llm", "hybrid"] = "fixed"
    user_profile: UserProfile | None = None
