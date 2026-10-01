from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.domain import UserProfile


class AnalyzeRequest(BaseModel):
    user_id: str = Field(min_length=1)
    jd_text: str = Field(min_length=20)
    company_name: str = Field(min_length=1)
    job_title: str | None = None
    employment_type: Literal["social", "campus", "intern"] = "social"
    question: str = "分析岗位匹配度、公司情况和预计薪资"
    target_location: str | None = None
    currency: str = "CNY"
    router_mode: Literal["fixed"] = "fixed"
    user_profile: UserProfile | None = None
    thread_id: str | None = None
