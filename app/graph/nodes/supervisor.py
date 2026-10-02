from __future__ import annotations

import logging
from time import perf_counter

from langchain_core.callbacks import get_usage_metadata_callback

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.common import timer, token_usage
from app.graph.state import JobAnalysisState
from app.schemas.domain import NodeError, NodeMetric, RouterDecision
from app.services.model import DeterministicAnalysisModel

logger = logging.getLogger(__name__)

MAX_ROUTER_DECISIONS = 8


def make_supervisor_node(deps: GraphDependencies):
    async def supervise(state: JobAnalysisState) -> dict:
        started_at = timer()
        decisions = state.get("router_decisions", [])
        if len(decisions) >= MAX_ROUTER_DECISIONS:
            decision = RouterDecision(
                next_agent="report",
                reason="已达到最大路由次数，进入降级报告以避免循环",
            )
            return {
                "next_agent": decision.next_agent,
                "router_decisions": [decision],
                "errors": [
                    NodeError(
                        node="supervisor",
                        message="LLM Router 达到最大决策次数，已强制进入报告节点",
                    )
                ],
                "metrics": [
                    NodeMetric(
                        node="supervisor",
                        latency_ms=max(0, round((perf_counter() - started_at) * 1000)),
                    )
                ],
                "step_count": 1,
            }

        completed_agents = list(state.get("completed_agents", []))
        degraded = False
        with get_usage_metadata_callback() as usage:
            try:
                decision = await deps.model.choose_next_agent(
                    question=state["question"],
                    completed_agents=completed_agents,
                )
            except Exception:
                logger.exception("Supervisor routing failed; using deterministic fallback")
                decision = await DeterministicAnalysisModel().choose_next_agent(
                    question=state["question"],
                    completed_agents=completed_agents,
                )
                degraded = True

        usage_values = token_usage(usage)
        result = {
            "next_agent": decision.next_agent,
            "router_decisions": [decision],
            "metrics": [
                NodeMetric(
                    node="supervisor",
                    latency_ms=max(0, round((perf_counter() - started_at) * 1000)),
                    **usage_values,
                    model_calls=1,
                )
            ],
            "step_count": 1,
        }
        if degraded:
            result["errors"] = [
                NodeError(
                    node="supervisor",
                    message="LLM 路由失败，已使用本地规则完成本次决策",
                )
            ]
        return result

    return supervise


def route_from_supervisor(
    state: JobAnalysisState,
) -> str:
    return state["next_agent"]
