from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select

from app.core.logging import request_id_var
from app.domain.enums import UserRole
from app.infrastructure.database.models.user import AuditLog, User
from app.infrastructure.database.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User
    entity_name = "User"

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def count(self) -> int:
        return int((await self.session.execute(select(func.count(User.id)))).scalar_one())

    async def create(self, *, username: str, password_hash: str, role: UserRole) -> User:
        user = User(username=username, password_hash=password_hash, role=role, is_active=True)
        return self.add(user)


class AuditRepository(BaseRepository[AuditLog]):
    model = AuditLog
    entity_name = "AuditLog"

    def record(
        self,
        *,
        actor_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_state=before_state,
            after_state=after_state,
            request_id=request_id_var.get(),
        )
        return self.add(entry)
