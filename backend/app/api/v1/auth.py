# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.api.route import DocumentedRoute
from app.application.services.auth import AuthService
from app.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.ratelimit import RateLimiter
from app.core.security import decode_access_token
from app.dependencies import CurrentUser, SessionDep, bearer_scheme
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/auth", tags=["Authentication & Users"], route_class=DocumentedRoute)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Вход: получение JWT access-токена",
    description=(
        "Аутентификация по логину/паролю (Argon2). Единственный публичный endpoint "
        "вместе с `/health*` — токен не требуется.\n\n"
        "- **200** — успешный вход: `access_token` (JWT HS256), `token_type: bearer`, "
        "`expires_in_minutes` (по умолчанию 60) и профиль пользователя.\n"
        "- **401** `authentication_failed` — неверные учётные данные или неактивный "
        "пользователь.\n"
        "- **422** `validation_error` — невалидное тело запроса.\n"
        "- **429** `rate_limited` — превышен лимит попыток: per-IP "
        "(RATE_LIMIT_LOGIN_PER_MINUTE, по умолчанию 10/мин) и per-username "
        "(RATE_LIMIT_LOGIN_PER_USERNAME_PER_MINUTE, по умолчанию 20/мин); "
        "заголовок `Retry-After` содержит паузу в секундах.\n\n"
        "Далее передавайте `Authorization: Bearer <access_token>` во все запросы. "
        "Быстрый старт (шаг 1 сценария login → upload → job → poll → observations → "
        "asset → review → map → export): docs/api/authentication.md, docs/api/workflows.md."
    ),
)
async def login(body: LoginRequest, request: Request, session: SessionDep) -> TokenResponse:
    settings = get_settings()
    limiter = RateLimiter(request.app.state.redis)
    client_host = request.client.host if request.client else "unknown"
    await limiter.check(f"login:ip:{client_host}", settings.rate_limit_login_per_minute)
    await limiter.check(
        f"login:user:{body.username}", settings.rate_limit_login_per_username_per_minute
    )
    service = AuthService(session, settings)
    token, user = await service.login(body.username, body.password)
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.jwt_access_token_expire_minutes,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/logout",
    summary="Отзыв текущего access-токена",
    description=(
        "Отзывает предъявленный токен: его `jti` помещается в Redis-denylist "
        "с TTL до естественного истечения; последующие запросы с этим токеном "
        "получают 401 `authentication_failed` (Token revoked).\n\n"
        '- **200** — токен отозван (`{"message": "logged out"}`).\n'
        "- **401** — токен отсутствует/невалиден/уже отозван.\n"
        "- Logout требует доступного Redis; при недоступности Redis проверка "
        "denylist для остальных запросов fail-open (доступность важнее отзыва), "
        "сам logout при этом завершится ошибкой.\n\n"
        "Идемпотентность: повторный logout тем же токеном снова вернёт 401 "
        "(токен уже отозван). См. docs/api/authentication.md."
    ),
    responses={
        200: {
            "model": MessageResponse,
            "description": "Токен отозван",
            "content": {"application/json": {"example": {"message": "logged out"}}},
        }
    },
)
async def logout(
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict:
    if credentials is None:
        raise AuthenticationError("Missing bearer token")
    settings = get_settings()
    payload = decode_access_token(
        credentials.credentials,
        secret=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    await AuthService(session, settings).logout(payload, request.app.state.redis)
    return {"message": "logged out"}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Профиль текущего пользователя",
    description=(
        "Возвращает профиль пользователя, разрешённого из Bearer-токена: "
        "id, username, email, роль, активность и дату создания.\n\n"
        "- **200** — профиль текущего пользователя.\n"
        "- **401** `authentication_failed` — токен отсутствует, просрочен, отозван "
        "или пользователь деактивирован.\n\n"
        "Используется frontend для проверки валидности сессии и отображения роли "
        "(VIEWER — только чтение, OPERATOR/SERVICE/ADMIN — мутации и медиа). "
        "См. docs/api/authentication.md."
    ),
)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
