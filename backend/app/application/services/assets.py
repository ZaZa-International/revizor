"""Asset registry operations: manual patch with optimistic locking.

PATCH values use presence semantics (exclude_unset): an explicit null clears
a field; clearing priority_override also clears priority_override_reason.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.history import AssetHistoryService
from app.application.services.risk import RiskScoringService
from app.core.exceptions import ConflictError, ValidationAppError
from app.domain.enums import (
    AuditAction,
    ConditionChangeSource,
    GeolocationStatus,
    LifecycleStatus,
)
from app.domain.geospatial.models import GeoPoint
from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.repositories.assets import AssetRepository, point_element
from app.infrastructure.database.repositories.users import AuditRepository

_PATCHABLE = {
    "display_name",
    "external_id",
    "lifecycle_status",
    "priority_override",
    "priority_override_reason",
}


class AssetService:
    def __init__(
        self, session: AsyncSession, risk: RiskScoringService, history: AssetHistoryService
    ) -> None:
        self._session = session
        self._assets = AssetRepository(session)
        self._risk = risk
        self._history = history
        self._audit = AuditRepository(session)

    async def patch_asset(
        self,
        asset_id: uuid.UUID,
        values: dict,
        *,
        actor_id: uuid.UUID | None,
        expected_version: int | None = None,
    ) -> Asset:
        asset = await self._assets.get_or_raise(asset_id)
        unknown = set(values) - _PATCHABLE - {"location", "expected_version"}
        if unknown:
            raise ValidationAppError(f"Fields not patchable: {sorted(unknown)}")
        if expected_version is not None and expected_version != asset.version:
            raise ConflictError("Asset version mismatch; reload and retry")

        before = {
            "display_name": asset.display_name,
            "external_id": asset.external_id,
            "lifecycle_status": asset.lifecycle_status.value,
            "priority_override": asset.priority_override,
            "current_priority": asset.current_priority,
            "version": asset.version,
        }
        updates: dict = {}
        for field in _PATCHABLE & set(values):
            value = values[field]
            if field == "lifecycle_status" and value is not None:
                value = LifecycleStatus(value)
            if field == "priority_override" and value is not None:
                if not 0 <= value <= 100:
                    raise ValidationAppError("priority_override must be within [0, 100]")
                if not values.get("priority_override_reason"):
                    raise ValidationAppError(
                        "priority_override_reason is required when overriding priority"
                    )
            updates[field] = value

        if "priority_override" in values and values["priority_override"] is None:
            updates["priority_override_reason"] = None

        if "location" in values and values["location"] is not None:
            loc = values["location"]
            try:
                point = GeoPoint(longitude=loc["longitude"], latitude=loc["latitude"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValidationAppError(f"Invalid location: {exc}") from exc
            updates["location"] = point_element(point)
            updates["geolocation_status"] = GeolocationStatus.CONFIRMED
            updates["location_accuracy_m"] = loc.get("accuracy_m", 5.0)

        if "priority_override" in updates:
            assessment = self._risk.assess(
                asset_type=asset.asset_type,
                severity=asset.current_severity,
                confidence=1.0,
                manual_override=updates["priority_override"],
            )
            await self._history.record_change(
                asset=asset,
                new_condition=asset.current_condition,
                new_severity=asset.current_severity,
                new_priority=assessment.priority,
                source=ConditionChangeSource.MANUAL_EDIT,
                detected_at=datetime.now(UTC),
                note="manual_priority_override",
            )
            updates["current_priority"] = assessment.priority
            updates["priority_band"] = assessment.band
            updates["priority_factors"] = assessment.factors
            updates["priority_policy_version"] = assessment.policy_version

        if not updates:
            return asset
        asset = await self._assets.update_with_version(asset, asset.version, updates)
        self._audit.record(
            actor_id=actor_id,
            action=AuditAction.UPDATE.value,
            entity_type="asset",
            entity_id=asset.id,
            before_state=before,
            after_state={k: str(v) for k, v in updates.items()},
        )
        await self._session.flush()
        return asset
