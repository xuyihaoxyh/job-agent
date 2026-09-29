from __future__ import annotations

import hashlib

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.common import completed, timer
from app.graph.state import JobAnalysisState
from app.schemas.domain import CompanyInfo, NodeError, RouteEvent, Source


def _source_id(url: str, index: int) -> str:
    digest = hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"company-{index}-{digest}"


def make_company_node(deps: GraphDependencies):
    async def research_company(state: JobAnalysisState) -> dict:
        started_at = timer()
        company_name = state["company_name"]
        query = f"{company_name} 公司 官网 业务 规模"
        try:
            results = await deps.search.search(query, max_results=5)
            sources = [
                Source(
                    id=_source_id(result.url, index),
                    title=result.title,
                    url=result.url,
                    snippet=result.snippet,
                )
                for index, result in enumerate(results, start=1)
            ]
            facts = [result.snippet for result in results if result.snippet][:5]
            info = CompanyInfo(
                company_name=company_name,
                summary=" ".join(facts[:2])
                if facts
                else "未找到足够可靠的公开公司信息。",
                facts=facts,
                confidence="high" if len(sources) >= 3 else "medium" if sources else "low",
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

