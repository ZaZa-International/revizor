from __future__ import annotations

from fastapi import APIRouter, Request

from app.application.services.auth import AuthService
from app.config import get_settings
from app.core.ratelimit import RateLimiter
from app.dependencies import CurrentUser, SessionDep
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, summary="Obtain JWT access token")
async def login(body: LoginRequest, request: Request, session: SessionDep) -> TokenResponse:
    settings = get_settings()
    limiter = RateLimiter(request.app.state.redis)
    client_host = request.client.host if request.client else "unknown"
    await limiter.check(f"login:{client_host}", settings.rate_limit_login_per_minute)
    service = AuthService(session, settings)
    token, user = await service.login(body.username, body.password)
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.jwt_access_token_expire_minutes,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse, summary="Current user profile")
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
