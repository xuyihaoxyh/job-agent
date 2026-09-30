from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.common import completed, timer
from app.graph.state import JobAnalysisState
from app.schemas.domain import NodeError, RouteEvent, SalaryInfo, Source
from app.tools.salary_calculator import estimate_monthly_salary


def _source_id(url: str, index: int) -> str:
    digest = hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"salary-{index}-{digest}"


def _compact_snippet(value: str, limit: int = 500) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[:limit].rstrip() + "…"


def _is_trusted_salary_source(url: str) -> bool:
    host = urlparse(url).netloc.casefold()
    return any(
        domain in host
        for domain in (
            "zhaopin.com",
            "liepin.com",
            "zhipin.com",
            "jobui.com",
            "kanzhun.com",
            "glassdoor.com",
            "levels.fyi",
        )
    )


def make_salary_node(deps: GraphDependencies):
    async def research_salary(state: JobAnalysisState) -> dict:
        started_at = timer()
        role_name = state["jd_info"].role_name or "相关岗位"
        location = state.get("target_location") or "中国"
        company_name = state["company_name"]
        query = f"{company_name} {location} {role_name} 薪资 招聘 月薪"
        try:
            results = await deps.search.search(query, max_results=5)
            estimate = estimate_monthly_salary(results)
            company_specific_samples = sum(
                1
                for result in results
                if company_name.casefold()
                in f"{result.title} {result.snippet}".casefold()
                and estimate_monthly_salary([result]).sample_count > 0
            )
            trusted_source_count = sum(
                1 for result in results if _is_trusted_salary_source(result.url)
            )
            sources = [
                Source(
                    id=_source_id(result.url, index),
                    title=result.title,
                    url=result.url,
                    snippet=_compact_snippet(result.snippet),
                )
                for index, result in enumerate(results, start=1)
            ]
            info = SalaryInfo(
                role_name=role_name,
                location=location,
                minimum=estimate.minimum,
                maximum=estimate.maximum,
                currency=state.get("currency", "CNY"),
                sample_count=estimate.sample_count,
                company_specific_samples=company_specific_samples,
                trusted_source_count=trusted_source_count,
                methodology="对可识别月薪区间去重、过滤明显异常值后，取上下界中位数。",
                caveats=[
                    "公开招聘样本不等同于正式 Offer，奖金、职级和年终奖未计入。",
                    (
                        "包含公司相关样本，但仍需结合具体部门和职级判断。"
                        if company_specific_samples
                        else "未识别到明确的公司专属样本，当前区间更接近同地区岗位市场参考。"
                    ),
                ],
                summary=(
                    f"基于 {estimate.sample_count} 个去重后的公开月薪区间计算，"
                    "仅作为市场参考。"
                    if estimate.minimum is not None
                    else "未从搜索结果中识别出可靠的月薪区间。"
                ),
                confidence=(
                    "high"
                    if estimate.sample_count >= 4
                    and company_specific_samples >= 2
                    and trusted_source_count >= 2
                    else "medium"
                    if estimate.sample_count >= 2
                    else "low"
                ),
                sources=sources,
            )
            return {
                "salary_info": info,
                "sources": sources,
                **completed("salary", started_at),
            }
        except Exception as exc:
            info = SalaryInfo(
                role_name=role_name,
                location=location,
                currency=state.get("currency", "CNY"),
                summary="薪资搜索失败，报告将使用降级结果。",
                caveats=["未能获得公开薪资样本。"],
                confidence="low",
            )
            result = completed("salary", started_at)
            result["route_events"] = [RouteEvent(node="salary", status="degraded")]
            return {
                "salary_info": info,
                "errors": [NodeError(node="salary", message=str(exc))],
                **result,
            }

    return research_salary
