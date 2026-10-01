from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.schemas.auth import AuthUser


async def get_current_user(request: Request) -> AuthUser:
    settings = request.app.state.settings
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    user = await request.app.state.auth.user_for_session(token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")
    return user
