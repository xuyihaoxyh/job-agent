from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.auth.dependencies import get_current_user
from app.schemas.auth import AuthUser
from app.schemas.history import AnalysisHistoryResponse

router = APIRouter(prefix="/api/v1/analyses", tags=["analysis-history"])


@router.get("", response_model=AnalysisHistoryResponse)
async def list_analyses(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    user: AuthUser = Depends(get_current_user),
) -> AnalysisHistoryResponse:
    items = await request.app.state.history.list_for_user(user.id, limit=limit)
    return AnalysisHistoryResponse(items=items)
