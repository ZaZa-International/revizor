"""FastAPI dependency injection: settings, DB session, storage, ML, queue, auth/RBAC."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.ml_provider import MLProvider
from app.application.interfaces.queue import JobQueue
from app.application.interfaces.storage import ObjectStorage
from app.config import Settings, get_settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError, ValidationAppError
from app.core.logging import actor_id_var, get_logger
from app.core.security import decode_access_token
from app.domain.enums import UserRole
from app.domain.geospatial.models import BoundingBox, CoordinateError
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.users import UserRepository
from app.infrastructure.database.session import Database

logger = get_logger(__name__)

bearer_scheme = HTTPBearer(
    bearerFormat="JWT",
    description=(
        "JWT Bearer-токен, полученный через POST /api/v1/auth/login. "
        "Заголовок: `Authorization: Bearer <access_token>`. Срок жизни — 60 минут "
        "(по умолчанию); после logout токен отзывается. Роли: ADMIN, OPERATOR, "
        "VIEWER, SERVICE. См. docs/api/authentication.md."
    ),
    auto_error=False,
)


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_storage(request: Request) -> ObjectStorage:
    return request.app.state.storage


def get_ml(request: Request) -> MLProvider:
    return request.app.state.ml


def get_queue(request: Request) -> JobQueue:
    return request.app.state.queue


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    database: Database = request.app.state.database
    async with database.session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        for key in session.info.get("storage_delete_keys", []):
            try:
                await request.app.state.storage.delete(key)
            except Exception:
                logger.warning("storage_delete_after_commit_failed", storage_key=key)


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
StorageDep = Annotated[ObjectStorage, Depends(get_storage)]
MLDep = Annotated[MLProvider, Depends(get_ml)]
QueueDep = Annotated[JobQueue, Depends(get_queue)]


async def get_current_user(
    request: Request,
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """Resolve the bearer token to an active user, rejecting revoked jti.

    Denylist policy: on Redis outage the check fails OPEN (availability over
    revocation) — already-issued tokens stay valid until natural expiry and
    the outage is logged. Logout itself still requires Redis.
    """
    if credentials is None:
        raise AuthenticationError("Missing bearer token")
    settings = get_settings()
    payload = decode_access_token(
        credentials.credentials,
        secret=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    jti = payload.get("jti")
    if jti:
        try:
            revoked = await request.app.state.redis.exists(f"jwt:deny:{jti}")
        except RedisError:
            logger.warning("jwt_denylist_unavailable_fail_open")
            revoked = 0
        if revoked:
            raise AuthenticationError("Token revoked")
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Invalid token subject") from exc
    user = await UserRepository(session).get(user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("User not found or inactive")
    actor_id_var.set(str(user.id))
    request.state.user = user
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def can_access_media(user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.OPERATOR, UserRole.SERVICE)


def require_roles(*roles: UserRole) -> Any:
    allowed = set(roles)

    async def checker(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise PermissionDeniedError(
                f"Role {user.role.value} is not allowed; requires one of "
                f"{sorted(r.value for r in allowed)}"
            )
        return user

    return checker


OperatorOrAdmin = Annotated[
    User, Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.SERVICE))
]
AnyAuthenticated = CurrentUser


def parse_bbox(bbox: str | None) -> BoundingBox | None:
    if bbox is None or not bbox.strip():
        return None
    try:
        return BoundingBox.parse(bbox)
    except CoordinateError as exc:
        raise ValidationAppError(str(exc)) from exc
