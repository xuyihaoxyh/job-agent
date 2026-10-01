from __future__ import annotations

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.common import completed, timer
from app.graph.state import JobAnalysisState
from app.schemas.domain import UserProfile


def make_intake_node(deps: GraphDependencies):
    async def intake(state: JobAnalysisState) -> dict:
        started_at = timer()
        jd_text = " ".join(state["jd_text"].split())
        company_name = state["company_name"].strip()
        if len(jd_text) < 20:
            raise ValueError("jd_text must contain at least 20 characters")
        if not company_name:
            raise ValueError("company_name is required")

        profile = state.get("user_profile")
        if profile is None:
            profile = await deps.profiles.get(state["user_id"])
        if profile is None:
            raise ValueError("user_profile is required for a user's first analysis")
        profile = UserProfile.model_validate(profile)

        return {
            "jd_text": jd_text,
            "company_name": company_name,
            "job_title": (state.get("job_title") or "").strip() or None,
            "employment_type": state.get("employment_type", "social"),
            "user_profile": profile,
            "target_location": state.get("target_location")
            or (profile.preferred_locations[0] if profile.preferred_locations else None),
            "currency": state.get("currency", "CNY").upper(),
            "status": "running",
            **completed("intake", started_at),
        }

    return intake
