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


@pytest.mark.asyncio
async def test_model_failures_use_deterministic_fallback(profile, search_results):
    class FailingModel:
        async def extract_jd(self, jd_text: str):
            raise RuntimeError("model unavailable")

        async def write_report(self, **kwargs):
            raise RuntimeError("model unavailable")

    graph = build_graph(
        GraphDependencies(
            model=FailingModel(),
            search=StaticSearchGateway(search_results),
            profiles=InMemoryProfiles(profile),
        )
    )

    result = await graph.ainvoke(graph_input(profile))

    assert result["status"] == "completed"
    assert result["jd_info"].required_skills
    assert result["final_report"].startswith("# 岗位分析报告")
    assert {error.node for error in result["errors"]} >= {"jd", "report"}
    degraded = {
        event.node for event in result["route_events"] if event.status == "degraded"
    }
    assert degraded >= {"jd", "report"}


@pytest.mark.asyncio
async def test_unrelated_search_results_produce_information_insufficient(profile):
    unrelated_results = [
        SearchResult(
            title="腾讯云解决方案",
            url="https://cloud.tencent.com/solution",
            snippet="腾讯提供云计算、游戏、社交和金融科技服务。",
        ),
        SearchResult(
            title="上海产品经理招聘 30K-50K",
            url="https://jobs.example/product",
            snippet="产品经理岗位，月薪30K-50K。",
        ),
    ]
    graph = build_graph(
        GraphDependencies(
            model=DeterministicAnalysisModel(),
            search=StaticSearchGateway(unrelated_results),
            profiles=InMemoryProfiles(profile),
        )
    )

    result = await graph.ainvoke(graph_input(profile))

    assert result["status"] == "completed"
    assert result["company_info"].businesses == []
    assert result["company_info"].company_type is None
    assert result["company_info"].sources == []
    assert result["salary_info"].minimum is None
    assert result["salary_info"].sample_count == 0
    assert result["salary_info"].sources == []
    assert "未找到能够明确对应" in result["final_report"]


@pytest.mark.asyncio
async def test_salary_falls_back_to_market_and_keeps_raw_search_attempts(profile):
    class QueryAwareSearch:
        async def search(self, query: str, *, max_results: int = 5):
            if "官网" in query:
                return [
                    SearchResult(
                        title="示例科技官网",
                        url="https://example.com",
                        snippet="示例科技是一家企业软件服务商。",
                    )
                ]
            if query.startswith("示例科技"):
                return [
                    SearchResult(
                        title="示例科技整体薪酬",
                        url="https://salary.example/company",
                        snippet="示例科技整体薪酬区间为6K-50K，未区分岗位。",
                    )
                ]
            return [
                SearchResult(
                    title="上海Java后端招聘 18K-25K",
                    url="https://jobs.example/one",
                    snippet="上海Java后端岗位月薪18K-25K。",
                ),
                SearchResult(
                    title="上海Java后端工程师 20K-30K",
                    url="https://jobs.example/two",
                    snippet="上海Java后端工程师薪资20K-30K。",
                ),
            ]

    graph = build_graph(
        GraphDependencies(
            model=DeterministicAnalysisModel(),
            search=QueryAwareSearch(),
            profiles=InMemoryProfiles(profile),
        )
    )

    result = await graph.ainvoke(graph_input(profile))
    salary = result["salary_info"]

    assert salary.data_scope == "market"
    assert salary.fallback_used is True
    assert salary.minimum == 19000
    assert salary.maximum == 27500
    assert len(salary.search_attempts) == 2
    assert salary.search_attempts[0].raw_result_count == 1
    assert salary.search_attempts[0].accepted_result_count == 0
    assert salary.search_attempts[0].sources[0].title == "示例科技整体薪酬"
    assert salary.search_attempts[1].accepted_result_count == 2
    assert {source.url for source in salary.sources} == {
        "https://jobs.example/one",
        "https://jobs.example/two",
    }
    assert "市场参考（降级结果）" in result["final_report"]
