from __future__ import annotations

import logging
from time import perf_counter

from langchain_core.callbacks import get_usage_metadata_callback

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.common import timer, token_usage
from app.graph.routers.hybrid import fallback_plan, validate_plan
from app.graph.state import JobAnalysisState
from app.schemas.domain import NodeError, NodeMetric

logger = logging.getLogger(__name__)


def make_planner_node(deps: GraphDependencies):
    async def create_plan(state: JobAnalysisState) -> dict:
        started_at = timer()
        degraded = False
        with get_usage_metadata_callback() as usage:
            try:
                proposed = await deps.model.create_analysis_plan(question=state["question"])
                decision = validate_plan(proposed)
            except Exception:
                logger.exception("Hybrid planning failed; using full-analysis fallback")
                decision = fallback_plan("模型规划失败")
                degraded = True

        result = {
            "analysis_plan": decision,
            "planned_agents": decision.final_agents,
            "metrics": [
                NodeMetric(
                    node="planner",
                    latency_ms=max(0, round((perf_counter() - started_at) * 1000)),
                    **token_usage(usage),
                    model_calls=1,
                )
            ],
            "step_count": 1,
        }
        if degraded:
            result["errors"] = [
                NodeError(
                    node="planner",
                    message="LLM 规划失败，已降级为全量分析",
                )
            ]
        return result

    return create_plan


def route_planned_agents(state: JobAnalysisState) -> list[str]:
    return list(state["planned_agents"])
