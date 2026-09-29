from __future__ import annotations

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.common import completed, timer
from app.graph.state import JobAnalysisState


def make_report_node(deps: GraphDependencies):
    async def write_report(state: JobAnalysisState) -> dict:
        started_at = timer()
        report = await deps.model.write_report(
            question=state["question"],
            jd_info=state["jd_info"],
            company_info=state["company_info"],
            salary_info=state["salary_info"],
            match_result=state["match_result"],
            user_profile=state["user_profile"],
        )
        return {
            "final_report": report,
            "status": "completed",
            **completed("report", started_at),
        }

    return write_report

