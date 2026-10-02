from __future__ import annotations

from app.graph.nodes.common import completed, timer
from app.graph.state import JobAnalysisState
from app.tools.match_scorer import score_match


async def match_candidate(state: JobAnalysisState) -> dict:
    started_at = timer()
    result = score_match(state["jd_info"], state["user_profile"])
    return {"match_result": result, **completed("match", started_at)}
