from __future__ import annotations

from typing import Protocol

from app.schemas.domain import (
    CompanyInfo,
    JDInfo,
    MatchResult,
    SalaryInfo,
    SearchResult,
    UserProfile,
)


class AnalysisModel(Protocol):
    async def extract_jd(self, jd_text: str) -> JDInfo: ...

    async def write_report(
        self,
        *,
        question: str,
        jd_info: JDInfo,
        company_info: CompanyInfo,
        salary_info: SalaryInfo,
        match_result: MatchResult,
        user_profile: UserProfile,
    ) -> str: ...


class SearchGateway(Protocol):
    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]: ...


class UserProfileReader(Protocol):
    async def get(self, user_id: str) -> UserProfile | None: ...

