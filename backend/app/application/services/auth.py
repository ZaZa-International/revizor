"""Authentication and user bootstrap."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token, hash_password, verify_password
from app.domain.enums import AuditAction, UserRole
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.users import AuditRepository, UserRepository


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._users = UserRepository(session)
        self._audit = AuditRepository(session)
        self._settings = settings

    async def login(self, username: str, password: str) -> tuple[str, User]:
        user = await self._users.get_by_username(username)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid username or password")
        token = create_access_token(
            subject=user.id,
            role=user.role.value,
            secret=self._settings.jwt_secret_key,
            algorithm=self._settings.jwt_algorithm,
            expires_minutes=self._settings.jwt_access_token_expire_minutes,
        )
        self._audit.record(
            actor_id=user.id,
            action=AuditAction.LOGIN.value,
            entity_type="user",
            entity_id=user.id,
        )
        return token, user

    async def bootstrap_admin(self) -> User | None:
        """Create the first admin only when no users exist and password is configured."""
        if not self._settings.bootstrap_admin_password:
            return None
        if await self._users.count() > 0:
            return None
        user = await self._users.create(
            username=self._settings.bootstrap_admin_username,
            password_hash=hash_password(self._settings.bootstrap_admin_password),
            role=UserRole.ADMIN,
        )
        self._audit.record(
            actor_id=None,
            action=AuditAction.CREATE.value,
            entity_type="user",
            entity_id=user.id,
            after_state={"username": user.username, "role": user.role.value, "bootstrap": True},
        )
        return user
