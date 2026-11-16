from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from geoalchemy2 import Geography
from sqlalchemy import Float, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.job import ProcessingJob
    from app.infrastructure.database.models.upload import Upload


class Route(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "routes"
    __table_args__ = (Index("ix_routes_created_at", "created_at"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    vehicle_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    track_geometry: Mapped[str | None] = mapped_column(
        Geography(geometry_type="LINESTRING", srid=4326), nullable=True
    )
    total_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    uploads: Mapped[list[Upload]] = relationship(back_populates="route")
    jobs: Mapped[list[ProcessingJob]] = relationship(back_populates="route")
