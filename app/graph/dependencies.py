from __future__ import annotations

from dataclasses import dataclass

from app.services.protocols import AnalysisModel, SearchGateway, UserProfileReader


@dataclass(frozen=True, slots=True)
class GraphDependencies:
    model: AnalysisModel
    search: SearchGateway
    profiles: UserProfileReader

