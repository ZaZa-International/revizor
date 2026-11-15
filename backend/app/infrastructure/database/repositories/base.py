"""Shared repository helpers: pagination, sorting, counting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.infrastructure.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


@dataclass
class Page(Generic[ModelT]):
    items: list[ModelT]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.page_size else 0


def clamp_pagination(page: int, page_size: int) -> tuple[int, int]:
    return max(1, page), max(1, min(MAX_PAGE_SIZE, page_size))


def apply_sorting(
    stmt: Select[Any],
    model: type[Base],
    sort_by: str | None,
    order: str,
    allowed: dict[str, Any],
) -> Select[Any]:
    column = allowed.get(sort_by or "")
    if column is None:
        column = getattr(model, "created_at", None)
    if column is None:
        return stmt
    return stmt.order_by(column.desc() if order == "desc" else column.asc())


async def paginate(
    session: AsyncSession,
    stmt: Select[Any],
    *,
    page: int,
    page_size: int,
) -> Page[Any]:
    page, page_size = clamp_pagination(page, page_size)
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await session.execute(count_stmt)).scalar_one()
    rows = (
        (await session.execute(stmt.offset((page - 1) * page_size).limit(page_size)))
        .scalars()
        .all()
    )
    return Page(items=list(rows), total=int(total), page=page, page_size=page_size)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]
    entity_name: str = "Entity"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: Any) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def get_or_raise(self, entity_id: Any) -> ModelT:
        instance = await self.get(entity_id)
        if instance is None:
            raise NotFoundError(self.entity_name, entity_id)
        return instance

    def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)

    async def flush(self) -> None:
        await self.session.flush()
