from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class Source(BaseModel):
    id: str
    title: str
    url: str
    snippet: str | None = None
    accessed_at: datetime = Field(default_factory=utc_now)


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""


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


class CompanyInfo(BaseModel):
    company_name: str
    summary: str
    facts: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"
    sources: list[Source] = Field(default_factory=list)


class SalaryInfo(BaseModel):
    role_name: str | None = None
    location: str | None = None
    minimum: int | None = Field(default=None, ge=0)
    maximum: int | None = Field(default=None, ge=0)
    currency: str = "CNY"
    period: Literal["month", "year"] = "month"
    summary: str
    confidence: Literal["low", "medium", "high"] = "low"
    sources: list[Source] = Field(default_factory=list)


class MatchResult(BaseModel):
    score: int = Field(ge=0, le=100)
    recommendation: str
    advantages: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)


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

