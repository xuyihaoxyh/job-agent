from __future__ import annotations

import logging

from langchain_core.callbacks import get_usage_metadata_callback

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.common import completed, timer, token_usage
from app.graph.state import JobAnalysisState
from app.schemas.domain import NodeError, RouteEvent
from app.services.model import DeterministicAnalysisModel

logger = logging.getLogger(__name__)


def make_report_node(deps: GraphDependencies):
    async def write_report(state: JobAnalysisState) -> dict:
        started_at = timer()
        degraded = False
        arguments = {
            "question": state["question"],
            "jd_info": state["jd_info"],
            "company_info": state.get("company_info"),
            "salary_info": state.get("salary_info"),
            "match_result": state.get("match_result"),
            "user_profile": state["user_profile"],
        }
        with get_usage_metadata_callback() as usage:
            try:
                report = await deps.model.write_report(**arguments)
            except Exception:
                logger.exception("Report generation failed; using deterministic fallback")
                report = await DeterministicAnalysisModel().write_report(**arguments)
                degraded = True
        node_result = completed("report", started_at, **token_usage(usage), model_calls=1)
        if degraded:
            node_result["route_events"] = [RouteEvent(node="report", status="degraded")]
            node_result["errors"] = [
                NodeError(node="report", message="模型生成报告失败，已使用本地模板降级")
            ]
        return {
            "final_report": report,
            "status": "completed",
            **node_result,
        }

    return write_report
