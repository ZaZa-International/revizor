"""Async engine / session factory lifecycle."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import Settings


class Database:
    def __init__(self, settings: Settings, *, null_pool: bool = False) -> None:
        if null_pool:
            self._engine: AsyncEngine = create_async_engine(
                settings.database_url,
                echo=settings.database_echo,
                poolclass=NullPool,
                pool_pre_ping=True,
            )
        else:
            self._engine = create_async_engine(
                settings.database_url,
                echo=settings.database_echo,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_pre_ping=True,
            )
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False, autoflush=False
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    def session(self) -> AsyncSession:
        return self._session_factory()

    async def dispose(self) -> None:
        await self._engine.dispose()
