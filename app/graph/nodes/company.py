from __future__ import annotations

import hashlib
import logging

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.common import completed, timer
from app.graph.state import JobAnalysisState
from app.schemas.domain import CompanyInfo, CompanySearchAttempt, NodeError, RouteEvent
from app.tools.company_analyzer import build_company_info, filter_company_results
from app.tools.source_quality import source_from_result

logger = logging.getLogger(__name__)


def _source_id(url: str, index: int) -> str:
    digest = hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"company-{index}-{digest}"


def make_company_node(deps: GraphDependencies):
    async def research_company(state: JobAnalysisState) -> dict:
        started_at = timer()
        company_name = state["company_name"]
        query = f"{company_name} 公司 官网 业务 规模"
        try:
            raw_results = await deps.search.search(query, max_results=5)
            results = filter_company_results(company_name, raw_results)
            accepted_urls = {result.url for result in results}
            sources = [
                source_from_result(
                    result,
                    source_id=_source_id(result.url, index),
                    company_name=company_name,
                    reason="搜索结果明确包含目标公司且可支撑公司事实",
                )
                for index, result in enumerate(results, start=1)
            ]
            info = build_company_info(
                company_name=company_name,
                jd_info=state["jd_info"],
                results=results,
                sources=sources,
            )
            info.search_attempts = [
                CompanySearchAttempt(
                    query=query,
                    raw_result_count=len(raw_results),
                    accepted_result_count=len(results),
                    sources=[
                        source_from_result(
                            item,
                            source_id=f"company-search-{_source_id(item.url, index)}",
                            company_name=company_name,
                            accepted=item.url in accepted_urls,
                            reason=(
                                "搜索结果明确包含目标公司，纳入候选证据"
                                if item.url in accepted_urls
                                else "未明确关联目标公司或内容不足，未用于结论"
                            ),
                        )
                        for index, item in enumerate(raw_results, start=1)
                    ],
                )
            ]
            return {
                "company_info": info,
                # Only evidence that survived sentence-level grounding may
                # become a final report source.
                "sources": info.sources,
                **completed("company", started_at),
            }
        except Exception:
            logger.exception("Company search failed for %s", company_name)
            info = CompanyInfo(
                company_name=company_name,
                summary="公司信息搜索失败，报告将使用降级结果。",
                confidence="low",
            )
            result = completed("company", started_at)
            result["route_events"] = [RouteEvent(node="company", status="degraded")]
            return {
                "company_info": info,
                "errors": [NodeError(node="company", message="公司公开信息搜索失败")],
                **result,
            }

    return research_company
