from __future__ import annotations

from typing import Protocol

from app.schemas.domain import (
    AnalysisPlan,
    CompanyInfo,
    JDInfo,
    MatchResult,
    RouterDecision,
    SalaryInfo,
    SearchResult,
    UserProfile,
)


class AnalysisModel(Protocol):
    async def extract_jd(self, jd_text: str) -> JDInfo: ...

    async def choose_next_agent(
        self,
        *,
        question: str,
        completed_agents: list[str],
    ) -> RouterDecision: ...

    async def create_analysis_plan(self, *, question: str) -> AnalysisPlan: ...

    async def write_report(
        self,
        *,
        question: str,
        jd_info: JDInfo,
        company_info: CompanyInfo | None,
        salary_info: SalaryInfo | None,
        match_result: MatchResult | None,
        user_profile: UserProfile,
    ) -> str: ...


class SearchGateway(Protocol):
    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]: ...


class UserProfileReader(Protocol):
    async def get(self, user_id: str) -> UserProfile | None: ...
