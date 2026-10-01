from __future__ import annotations

import hashlib

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.common import completed, timer
from app.graph.state import JobAnalysisState
from app.schemas.domain import CompanyInfo, NodeError, RouteEvent, Source
from app.tools.company_analyzer import build_company_info, filter_company_results


def _source_id(url: str, index: int) -> str:
    digest = hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"company-{index}-{digest}"


def _compact_snippet(value: str, limit: int = 500) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[:limit].rstrip() + "…"


def make_company_node(deps: GraphDependencies):
    async def research_company(state: JobAnalysisState) -> dict:
        started_at = timer()
        company_name = state["company_name"]
        query = f"{company_name} 公司 官网 业务 规模"
        try:
            raw_results = await deps.search.search(query, max_results=5)
            results = filter_company_results(company_name, raw_results)
            sources = [
                Source(
                    id=_source_id(result.url, index),
                    title=result.title,
                    url=result.url,
                    snippet=_compact_snippet(result.snippet),
                )
                for index, result in enumerate(results, start=1)
            ]
            info = build_company_info(
                company_name=company_name,
                jd_info=state["jd_info"],
                results=results,
                sources=sources,
            )
            return {
                "company_info": info,
                "sources": sources,
                **completed("company", started_at),
            }
        except Exception as exc:
            info = CompanyInfo(
                company_name=company_name,
                summary="公司信息搜索失败，报告将使用降级结果。",
                confidence="low",
            )
            result = completed("company", started_at)
            result["route_events"] = [RouteEvent(node="company", status="degraded")]
            return {
                "company_info": info,
                "errors": [NodeError(node="company", message=str(exc))],
                **result,
            }

    return research_company
