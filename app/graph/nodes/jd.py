from __future__ import annotations

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.common import completed, timer
from app.graph.state import JobAnalysisState


def make_jd_node(deps: GraphDependencies):
    async def extract_jd(state: JobAnalysisState) -> dict:
        started_at = timer()
        jd_info = await deps.model.extract_jd(state["jd_text"])
        if state.get("job_title"):
            jd_info = jd_info.model_copy(update={"role_name": state["job_title"]})
        return {"jd_info": jd_info, **completed("jd", started_at)}

    return extract_jd
