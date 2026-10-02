from __future__ import annotations

from app.schemas.domain import AnalysisPlan, PlanDecision

ALL_BUSINESS_AGENTS = ["company", "salary", "match"]


def validate_plan(plan: AnalysisPlan) -> PlanDecision:
    """Validate execution invariants without reinterpreting user intent."""
    proposed = list(plan.required_agents)
    final = list(dict.fromkeys(proposed))
    reasons: list[str] = []

    if len(final) != len(proposed):
        reasons.append("已删除重复节点")
    if not final:
        final = list(ALL_BUSINESS_AGENTS)
        reasons.append("模型未选择任何节点，已降级为全量分析")

    return PlanDecision(
        proposed_agents=proposed,
        final_agents=final,
        reason=plan.reason,
        overridden=final != proposed,
        policy_reason="；".join(reasons) or "模型计划满足工作流约束",
    )


def fallback_plan(reason: str) -> PlanDecision:
    return PlanDecision(
        proposed_agents=[],
        final_agents=list(ALL_BUSINESS_AGENTS),
        reason=reason,
        overridden=True,
        policy_reason="Planner 调用失败，已降级为全量分析",
    )
