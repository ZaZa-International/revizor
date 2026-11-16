from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, select

from app.domain.enums import MediaType
from app.infrastructure.database.models.stored_file import StoredFile
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.repositories.base import (
    BaseRepository,
    Page,
    apply_sorting,
    like_contains,
    paginate,
)


class UploadRepository(BaseRepository[Upload]):
    model = Upload
    entity_name = "Upload"

    async def get_by_checksum(self, checksum: str) -> Upload | None:
        stmt = select(Upload).where(Upload.checksum_sha256 == checksum)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    def filtered_stmt(
        self,
        *,
        media_type: MediaType | None = None,
        route_id: uuid.UUID | None = None,
        uploaded_by: uuid.UUID | None = None,
        search: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Select[Any]:
        stmt = select(Upload)
        if media_type is not None:
            stmt = stmt.where(Upload.media_type == media_type)
        if route_id is not None:
            stmt = stmt.where(Upload.route_id == route_id)
        if uploaded_by is not None:
            stmt = stmt.where(Upload.uploaded_by == uploaded_by)
        if search:
            stmt = stmt.where(Upload.original_filename.ilike(like_contains(search), escape="\\"))
        if date_from is not None:
            stmt = stmt.where(Upload.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Upload.created_at <= date_to)
        return stmt

    async def list_paginated(
        self,
        stmt: Select[Any],
        *,
        page: int,
        page_size: int,
        sort_by: str | None,
        order: str,
    ) -> Page[Upload]:
        stmt = apply_sorting(
            stmt,
            Upload,
            sort_by,
            order,
            {
                "created_at": Upload.created_at,
                "file_size": Upload.file_size,
                "original_filename": Upload.original_filename,
            },
        )
        return await paginate(self.session, stmt, page=page, page_size=page_size)


class StoredFileRepository(BaseRepository[StoredFile]):
    model = StoredFile
    entity_name = "StoredFile"
