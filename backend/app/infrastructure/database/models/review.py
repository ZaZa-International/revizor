from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import ReviewDecision
from app.infrastructure.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class Review(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only operator action. History is never overwritten."""

    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint(
            "observation_id IS NOT NULL OR defect_id IS NOT NULL", name="review_target_present"
        ),
        CheckConstraint(
            "corrected_severity IS NULL OR (corrected_severity >= 1 AND corrected_severity <= 5)",
            name="corrected_severity_range",
        ),
        Index("ix_reviews_created_at", "created_at"),
    )

    observation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("observations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    defect_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("defects.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    decision: Mapped[ReviewDecision] = mapped_column(
        Enum(ReviewDecision, name="review_decision"), nullable=False
    )
    corrected_asset_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    corrected_condition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    corrected_defect_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    corrected_severity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
