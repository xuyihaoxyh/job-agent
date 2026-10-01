from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class Source(BaseModel):
    id: str
    title: str
    url: str
    snippet: str | None = None
    accessed_at: datetime = Field(default_factory=utc_now)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source URL must use http or https")
        return value


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("search result URL must use http or https")
        return value


class UserProfile(BaseModel):
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: str | None = None
    years_of_experience: float | None = Field(default=None, ge=0)
    experiences: list[str] = Field(default_factory=list)


class JDInfo(BaseModel):
    role_name: str | None = None
    seniority: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    min_experience_years: float | None = Field(default=None, ge=0)
    education_requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)


class CompanyFact(BaseModel):
    claim: str
    source_ids: list[str] = Field(default_factory=list)


class CompanyInfo(BaseModel):
    company_name: str
    summary: str
    company_type: str | None = None
    headquarters: str | None = None
    businesses: list[str] = Field(default_factory=list)
    employee_scale: str | None = None
    role_relevance: str | None = None
    caveats: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    evidence: list[CompanyFact] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"
    sources: list[Source] = Field(default_factory=list)


class SalarySearchAttempt(BaseModel):
    scope: Literal["company", "market"]
    query: str
    raw_result_count: int = Field(ge=0)
    accepted_result_count: int = Field(ge=0)
    sources: list[Source] = Field(default_factory=list)


class SalaryInfo(BaseModel):
    role_name: str | None = None
    role_source: Literal["user", "jd", "inferred"] | None = None
    employment_type: Literal["social", "campus", "intern"] = "social"
    location: str | None = None
    minimum: int | None = Field(default=None, ge=0)
    maximum: int | None = Field(default=None, ge=0)
    currency: str = "CNY"
    period: Literal["month", "year"] = "month"
    summary: str
    sample_count: int = Field(default=0, ge=0)
    company_specific_samples: int = Field(default=0, ge=0)
    trusted_source_count: int = Field(default=0, ge=0)
    methodology: str = "未获得足够样本"
    caveats: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"
    data_scope: Literal["company", "market", "insufficient"] = "insufficient"
    fallback_used: bool = False
    search_attempts: list[SalarySearchAttempt] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)


class MatchScoreDimension(BaseModel):
    key: Literal["skills", "experience", "education"]
    label: str
    score: int = Field(ge=0)
    max_score: int = Field(gt=0)
    detail: str


class MatchResult(BaseModel):
    score: int = Field(ge=0, le=100)
    recommendation: str
    advantages: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    score_type: Literal["rule_based"] = "rule_based"
    score_dimensions: list[MatchScoreDimension] = Field(default_factory=list)
    scoring_note: str = (
        "规则匹配分仅依据结构化技能、经验和学历计算，不代表面试或录用概率。"
    )


class RouteEvent(BaseModel):
    node: str
    status: Literal["started", "completed", "failed", "degraded"]
    timestamp: datetime = Field(default_factory=utc_now)


class NodeError(BaseModel):
    node: str
    message: str
    recoverable: bool = True
    timestamp: datetime = Field(default_factory=utc_now)


class NodeMetric(BaseModel):
    node: str
    latency_ms: int = Field(ge=0)
    token_usage: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
