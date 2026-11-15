from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from geoalchemy2 import Geography
from sqlalchemy import CheckConstraint, Enum, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import GeolocationStatus, LifecycleStatus, PriorityBand
from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.defect import Defect
    from app.infrastructure.database.models.observation import Observation


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A physical infrastructure object with a stable identity across surveys."""

    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "current_severity IS NULL OR (current_severity >= 1 AND current_severity <= 5)",
            name="current_severity_range",
        ),
        CheckConstraint(
            "current_priority IS NULL OR (current_priority >= 0 AND current_priority <= 100)",
            name="current_priority_range",
        ),
        CheckConstraint(
            "priority_override IS NULL OR (priority_override >= 0 AND priority_override <= 100)",
            name="priority_override_range",
        ),
        CheckConstraint(
            "(location IS NULL) = (geolocation_status IN ('UNAVAILABLE', 'INVALID'))",
            name="location_matches_status",
        ),
    )

    external_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=True
    )
    location_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    geolocation_status: Mapped[GeolocationStatus] = mapped_column(
        Enum(GeolocationStatus, name="geolocation_status"),
        nullable=False,
        default=GeolocationStatus.UNAVAILABLE,
        index=True,
    )
    current_condition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_severity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_priority: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    priority_band: Mapped[PriorityBand | None] = mapped_column(
        Enum(PriorityBand, name="priority_band"), nullable=True, index=True
    )
    priority_factors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    priority_policy_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    priority_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_status: Mapped[LifecycleStatus] = mapped_column(
        Enum(LifecycleStatus, name="lifecycle_status"),
        nullable=False,
        default=LifecycleStatus.ACTIVE,
        index=True,
    )
    first_observed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_observed_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    observations: Mapped[list[Observation]] = relationship(back_populates="asset")
    defects: Mapped[list[Defect]] = relationship(back_populates="asset")
