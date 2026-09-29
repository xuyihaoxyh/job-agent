from __future__ import annotations

import hashlib

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.common import completed, timer
from app.graph.state import JobAnalysisState
from app.schemas.domain import NodeError, RouteEvent, SalaryInfo, Source
from app.tools.salary_calculator import extract_monthly_salary_range


def _source_id(url: str, index: int) -> str:
    digest = hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"salary-{index}-{digest}"


def make_salary_node(deps: GraphDependencies):
    async def research_salary(state: JobAnalysisState) -> dict:
        started_at = timer()
        role_name = state["jd_info"].role_name or "相关岗位"
        location = state.get("target_location") or "中国"
        query = f"{location} {role_name} 薪资 招聘 月薪"
        try:
            results = await deps.search.search(query, max_results=5)
            minimum, maximum = extract_monthly_salary_range(results)
            sources = [
                Source(
                    id=_source_id(result.url, index),
                    title=result.title,
                    url=result.url,
                    snippet=result.snippet,
                )
                for index, result in enumerate(results, start=1)
            ]
            info = SalaryInfo(
                role_name=role_name,
                location=location,
                minimum=minimum,
                maximum=maximum,
                currency=state.get("currency", "CNY"),
                summary=(
                    "区间由搜索结果中可识别的月薪样本计算，仅作为市场参考。"
                    if minimum is not None
                    else "未从搜索结果中识别出可靠的月薪区间。"
                ),
                confidence=(
                    "high"
                    if minimum is not None and len(sources) >= 3
                    else "medium"
                    if minimum is not None
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

