from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import ConditionChangeSource
from app.infrastructure.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class AssetConditionHistory(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """State change of an asset with explicit source.

    is_physical_change=False marks ML prediction fluctuations that are NOT
    confirmed physical changes of the object.
    """

    __tablename__ = "asset_condition_history"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    observation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("observations.id", ondelete="SET NULL"), nullable=True
    )
    review_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reviews.id", ondelete="SET NULL"), nullable=True
    )
    change_source: Mapped[ConditionChangeSource] = mapped_column(
        Enum(ConditionChangeSource, name="condition_change_source"), nullable=False
    )
    previous_condition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_condition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_severity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_severity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_priority: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_priority: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_physical_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
