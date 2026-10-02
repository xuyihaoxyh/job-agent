from __future__ import annotations

import logging

from langchain_core.callbacks import get_usage_metadata_callback

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.common import completed, timer, token_usage
from app.graph.state import JobAnalysisState
from app.schemas.domain import NodeError, RouteEvent
from app.services.model import DeterministicAnalysisModel

logger = logging.getLogger(__name__)


def make_jd_node(deps: GraphDependencies):
    async def extract_jd(state: JobAnalysisState) -> dict:
        started_at = timer()
        degraded = False
        with get_usage_metadata_callback() as usage:
            try:
                jd_info = await deps.model.extract_jd(state["jd_text"])
            except Exception:
                logger.exception("JD extraction failed; using deterministic fallback")
                jd_info = await DeterministicAnalysisModel().extract_jd(state["jd_text"])
                degraded = True
        if state.get("job_title"):
            jd_info = jd_info.model_copy(update={"role_name": state["job_title"]})
        node_result = completed("jd", started_at, **token_usage(usage), model_calls=1)
        if degraded:
            node_result["route_events"] = [RouteEvent(node="jd", status="degraded")]
            node_result["errors"] = [
                NodeError(node="jd", message="模型解析JD失败，已使用本地规则降级")
            ]
        return {
            "jd_info": jd_info,
            **node_result,
        }

    return extract_jd
