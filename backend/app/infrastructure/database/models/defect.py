from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Column,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import DefectStatus
from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.asset import Asset
    from app.infrastructure.database.models.observation import Observation

defect_observations = Table(
    "defect_observations",
    Base.metadata,
    Column(
        "defect_id",
        ForeignKey("defects.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "observation_id",
        ForeignKey("observations.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Defect(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A concrete problem of a physical asset, confirmed by >=1 observations."""

    __tablename__ = "defects"
    __table_args__ = (CheckConstraint("severity >= 1 AND severity <= 5", name="severity_range"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    defect_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DefectStatus] = mapped_column(
        Enum(DefectStatus, name="defect_status"),
        nullable=False,
        default=DefectStatus.OPEN,
        index=True,
    )
    first_detected_at: Mapped[datetime] = mapped_column(nullable=False)
    last_detected_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    asset: Mapped[Asset] = relationship(back_populates="defects")
    observations: Mapped[list[Observation]] = relationship(
        secondary=defect_observations, backref="defects"
    )
