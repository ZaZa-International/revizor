"""Defect registry writes: operator PATCH with the domain transition matrix.

Presence semantics (exclude_unset): explicit null description clears it.
REJECTED is terminal via API; RESOLVED sets resolved_at, reopen clears it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationAppError
from app.domain.defects.transitions import InvalidDefectTransitionError, assert_defect_transition
from app.domain.enums import AuditAction, DefectStatus
from app.infrastructure.database.models.defect import Defect
from app.infrastructure.database.repositories.defects import DefectRepository
from app.infrastructure.database.repositories.users import AuditRepository

_PATCHABLE = {"status", "severity", "description"}


class DefectService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._defects = DefectRepository(session)
        self._audit = AuditRepository(session)

    async def patch_defect(
        self, defect_id: uuid.UUID, values: dict, *, actor_id: uuid.UUID | None
    ) -> Defect:
        defect = await self._defects.get_or_raise(defect_id)
        unknown = set(values) - _PATCHABLE
        if unknown:
            raise ValidationAppError(f"Fields not patchable: {sorted(unknown)}")
        before = {
            "status": defect.status.value,
            "severity": defect.severity,
            "description": defect.description,
        }
        if values.get("status") is not None:
            target = DefectStatus(values["status"])
            try:
                assert_defect_transition(defect.status, target)
            except InvalidDefectTransitionError as exc:
                raise ValidationAppError(str(exc)) from exc
            defect.status = target
            defect.resolved_at = datetime.now(UTC) if target == DefectStatus.RESOLVED else None
        if values.get("severity") is not None:
            defect.severity = values["severity"]
        if "description" in values:
            defect.description = values["description"]
        self._audit.record(
            actor_id=actor_id,
            action=AuditAction.UPDATE.value,
            entity_type="defect",
            entity_id=defect.id,
            before_state=before,
            after_state={
                "status": defect.status.value,
                "severity": defect.severity,
                "description": defect.description,
            },
        )
        await self._session.flush()
        await self._session.refresh(defect)
        return defect
