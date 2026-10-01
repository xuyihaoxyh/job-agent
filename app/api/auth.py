from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.dependencies import get_current_user
from app.auth.repository import DuplicateUserError
from app.schemas.auth import (
    AuthResponse,
    AuthUser,
    LoginRequest,
    RegisterRequest,
    UpdateAccountRequest,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request, response: Response) -> AuthResponse:
    auth = request.app.state.auth
    try:
        user = await auth.create_user(
            username=payload.username,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
        )
    except DuplicateUserError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    token = await auth.create_session(user.id)
    _set_session_cookie(response, request, token)
    return AuthResponse(user=user)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> AuthResponse:
    auth = request.app.state.auth
    client_host = request.client.host if request.client else "unknown"
    rate_key = request.app.state.login_limiter.key(client_host, payload.login)
    if not await request.app.state.login_limiter.allowed(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过多，请稍后再试",
        )
    user = await auth.authenticate(payload.login, payload.password)
    if user is None:
        await request.app.state.login_limiter.record_failure(rate_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名/邮箱或密码错误"
        )
    await request.app.state.login_limiter.reset(rate_key)
    token = await auth.create_session(user.id)
    _set_session_cookie(response, request, token)
    return AuthResponse(user=user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    settings = request.app.state.settings
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await request.app.state.auth.delete_session(token)
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=AuthResponse)
async def me(user: AuthUser = Depends(get_current_user)) -> AuthResponse:
    return AuthResponse(user=user)


@router.patch("/me", response_model=AuthResponse)
async def update_me(
    payload: UpdateAccountRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> AuthResponse:
    updated = await request.app.state.auth.update_display_name(user.id, payload.display_name)
    return AuthResponse(user=updated)
