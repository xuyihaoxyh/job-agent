from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.schemas.auth import AuthUser
from app.schemas.domain import UserProfile


router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


class ProfileResponse(BaseModel):
    profile: UserProfile | None


@router.get("", response_model=ProfileResponse)
async def get_profile(
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> ProfileResponse:
    profile = await request.app.state.profiles.get(user.id)
    return ProfileResponse(profile=profile)


@router.put("", response_model=ProfileResponse)
async def save_profile(
    profile: UserProfile,
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> ProfileResponse:
    await request.app.state.profiles.upsert(user.id, profile)
    return ProfileResponse(profile=profile)
