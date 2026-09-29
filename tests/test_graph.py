from __future__ import annotations

import asyncio
from time import perf_counter

import pytest

from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.mcp.client import StaticSearchGateway
from app.schemas.domain import SearchResult, UserProfile
from app.services.model import DeterministicAnalysisModel


class InMemoryProfiles:
    def __init__(self, profile: UserProfile | None = None) -> None:
        self.profile = profile

    async def get(self, user_id: str) -> UserProfile | None:
        return self.profile


class SlowSearch:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results

    async def search(self, query: str, *, max_results: int = 5):
        await asyncio.sleep(0.1)
        return self.results[:max_results]


def graph_input(profile: UserProfile) -> dict:
    return {
        "user_id": "user-1",
        "question": "分析岗位匹配度和薪资",
        "jd_text": "招聘Java后端工程师，要求3年经验，熟悉Java、Spring Boot、MySQL、Redis和Kubernetes。负责核心服务开发。",
        "company_name": "示例科技",
        "user_profile": profile,
        "target_location": "上海",
        "currency": "CNY",
        "router_mode": "fixed",
    }


@pytest.mark.asyncio
async def test_fixed_graph_completes_all_nodes(profile, search_results):
    graph = build_graph(
        GraphDependencies(
            model=DeterministicAnalysisModel(),
            search=StaticSearchGateway(search_results),
            profiles=InMemoryProfiles(profile),
        )
    )
    result = await graph.ainvoke(graph_input(profile))

    assert result["status"] == "completed"
    assert set(result["completed_agents"]) == {
        "intake",
        "jd",
        "company",
        "salary",
        "match",
        "report",
    }
    assert result["match_result"].score >= 60
    assert result["salary_info"].minimum is not None
    assert result["final_report"].startswith("# 岗位分析报告")
    assert len(result["sources"]) >= 3


@pytest.mark.asyncio
async def test_search_branches_run_in_parallel(profile, search_results):
    graph = build_graph(
        GraphDependencies(
            model=DeterministicAnalysisModel(),
            search=SlowSearch(search_results),
            profiles=InMemoryProfiles(profile),
        )
    )
    started = perf_counter()
    await graph.ainvoke(graph_input(profile))
    elapsed = perf_counter() - started

    # Company and salary each sleep 100ms. Sequential execution would exceed 200ms.
    assert elapsed < 0.19


@pytest.mark.asyncio
async def test_search_failure_produces_degraded_report(profile):
    class FailingSearch:
        async def search(self, query: str, *, max_results: int = 5):
            raise RuntimeError("search unavailable")

    graph = build_graph(
        GraphDependencies(
            model=DeterministicAnalysisModel(),
            search=FailingSearch(),
            profiles=InMemoryProfiles(profile),
        )
    )
    result = await graph.ainvoke(graph_input(profile))

    assert result["status"] == "completed"
    assert len(result["errors"]) == 2
    assert result["company_info"].confidence == "low"
    assert result["salary_info"].confidence == "low"

