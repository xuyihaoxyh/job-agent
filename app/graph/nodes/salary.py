from __future__ import annotations

import hashlib
import logging
from urllib.parse import urlparse

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.common import completed, timer
from app.graph.state import JobAnalysisState
from app.schemas.domain import (
    NodeError,
    RouteEvent,
    SalaryInfo,
    SalarySearchAttempt,
    Source,
)
from app.tools.role_resolver import resolve_salary_search_role
from app.tools.salary_calculator import (
    estimate_monthly_salary,
    filter_salary_results,
    filter_valid_salary_results,
    focus_salary_result_on_role,
    result_is_company_salary_sample,
)

logger = logging.getLogger(__name__)


def _source_id(url: str, index: int) -> str:
    digest = hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"salary-{index}-{digest}"


def _compact_snippet(value: str, limit: int = 500) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[:limit].rstrip() + "…"


def _sources_for_results(results, *, prefix: str) -> list[Source]:
    return [
        Source(
            id=f"{prefix}-{_source_id(result.url, index)}",
            title=result.title,
            url=result.url,
            snippet=_compact_snippet(result.snippet),
        )
        for index, result in enumerate(results, start=1)
    ]


def _is_trusted_salary_source(url: str) -> bool:
    host = urlparse(url).netloc.casefold()
    return any(
        host == domain or host.endswith(f".{domain}")
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
        resolved_role = resolve_salary_search_role(
            explicit_title=state.get("job_title"),
            jd_info=state["jd_info"],
            jd_text=state["jd_text"],
        )
        role_name = resolved_role.specific_name
        market_role_name = resolved_role.market_name
        location = state.get("target_location") or "中国"
        company_name = state["company_name"]
        employment_type = state.get("employment_type", "social")
        employment_query = {
            "social": "社会招聘 社招",
            "campus": "校园招聘 校招",
            "intern": "实习招聘 实习",
        }[employment_type]
        company_query = (
            f"{company_name} {location} {role_name} {employment_query} 薪资 月薪"
        )
        try:
            raw_company_results = await deps.search.search(company_query, max_results=8)
            company_context_results = filter_salary_results(
                raw_company_results,
                role_name=role_name,
                location=location,
                employment_type=employment_type,
            )
            company_pairs = []
            for result in company_context_results:
                if not result_is_company_salary_sample(
                    result,
                    company_name=company_name,
                    role_name=role_name,
                ):
                    continue
                focused = focus_salary_result_on_role(result, role_name=role_name)
                if focused and estimate_monthly_salary([focused]).sample_count > 0:
                    company_pairs.append((result, focused))
            company_results = [original for original, _ in company_pairs]
            company_calculation_results = [focused for _, focused in company_pairs]
            attempts = [
                SalarySearchAttempt(
                    scope="company",
                    query=company_query,
                    raw_result_count=len(raw_company_results),
                    accepted_result_count=len(company_results),
                    sources=_sources_for_results(
                        raw_company_results,
                        prefix="salary-search-company",
                    ),
                )
            ]

            fallback_used = not company_results
            fallback_error: Exception | None = None
            results = company_results
            calculation_results = company_calculation_results
            data_scope = "company" if company_results else "insufficient"
            if fallback_used:
                market_query = (
                    f"{location} {market_role_name} {employment_query} 工资 薪资 月薪"
                )
                try:
                    raw_market_results = await deps.search.search(
                        market_query, max_results=8
                    )
                    market_context_results = filter_salary_results(
                        raw_market_results,
                        role_name=market_role_name,
                        location=location,
                        employment_type=employment_type,
                    )
                    market_results = filter_valid_salary_results(market_context_results)
                    attempts.append(
                        SalarySearchAttempt(
                            scope="market",
                            query=market_query,
                            raw_result_count=len(raw_market_results),
                            accepted_result_count=len(market_results),
                            sources=_sources_for_results(
                                raw_market_results,
                                prefix="salary-search-market",
                            ),
                        )
                    )
                    results = market_results
                    calculation_results = market_results
                    if market_results:
                        data_scope = "market"
                except Exception as exc:
                    logger.exception("Salary market fallback search failed")
                    fallback_error = exc
                    attempts.append(
                        SalarySearchAttempt(
                            scope="market",
                            query=market_query,
                            raw_result_count=0,
                            accepted_result_count=0,
                        )
                    )

            estimate = estimate_monthly_salary(calculation_results)
            company_specific_samples = sum(
                1
                for result in results
                if result_is_company_salary_sample(
                    result,
                    company_name=company_name,
                    role_name=role_name,
                )
            )
            trusted_source_count = sum(
                1 for result in results if _is_trusted_salary_source(result.url)
            )
            sources = _sources_for_results(results, prefix="salary-evidence")
            if data_scope == "company":
                summary = (
                    f"基于 {estimate.sample_count} 个去重后的公司相关月薪区间计算，"
                    "仅作为岗位参考。"
                )
            elif data_scope == "market":
                summary = (
                    f"未找到可靠的{company_name}专属样本，已降级为基于 "
                    f"{estimate.sample_count} 个{location}{market_role_name}公开月薪区间的市场参考。"
                )
            else:
                summary = (
                    "公司专属搜索未识别出可靠的月薪区间，市场降级搜索执行失败。"
                    if fallback_error
                    else "公司专属搜索及同地区岗位市场搜索均未识别出可靠的月薪区间。"
                )
            info = SalaryInfo(
                role_name=role_name,
                role_source=resolved_role.source,
                employment_type=employment_type,
                location=location,
                minimum=estimate.minimum,
                maximum=estimate.maximum,
                currency=state.get("currency", "CNY"),
                sample_count=estimate.sample_count,
                company_specific_samples=company_specific_samples,
                trusted_source_count=trusted_source_count,
                methodology=(
                    "先检索公司专属岗位；无有效样本时降级检索同城市同岗位市场数据。"
                    "对合格月薪区间去重并过滤明显异常值后，取上下界中位数。"
                ),
                caveats=[
                    "公开招聘样本不等同于正式 Offer，奖金、职级和年终奖未计入。",
                    (
                        "当前区间来自目标公司的相关岗位样本，仍需结合具体部门和职级判断。"
                        if data_scope == "company"
                        else "当前区间是同地区同岗位市场参考，不代表目标公司的实际 Offer。"
                        if data_scope == "market"
                        else "没有公开薪资证据不代表目标公司没有相关岗位。"
                    ),
                    *(
                        [
                            f"JD 未提供明确岗位标题，搜索岗位由系统推断为“{role_name}”；"
                            "建议填写岗位名称后重新分析。"
                        ]
                        if resolved_role.source == "inferred"
                        else []
                    ),
                ],
                summary=summary,
                confidence=(
                    "high"
                    if data_scope == "company"
                    and estimate.sample_count >= 4
                    and company_specific_samples >= 2
                    and trusted_source_count >= 2
                    else "medium"
                    if estimate.sample_count >= 2 and data_scope != "insufficient"
                    else "low"
                ),
                data_scope=data_scope,
                fallback_used=fallback_used,
                search_attempts=attempts,
                sources=sources,
            )
            node_result = completed("salary", started_at)
            response = {
                "salary_info": info,
                "sources": sources,
                **node_result,
            }
            if fallback_error:
                response["errors"] = [
                    NodeError(node="salary", message="市场薪资降级搜索失败")
                ]
                response["route_events"] = [
                    RouteEvent(node="salary", status="degraded")
                ]
            return response
        except Exception:
            logger.exception("Salary search failed for %s / %s", company_name, role_name)
            info = SalaryInfo(
                role_name=role_name,
                role_source=resolved_role.source,
                employment_type=employment_type,
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
                "errors": [NodeError(node="salary", message="薪资公开信息搜索失败")],
                **result,
            }

    return research_salary
