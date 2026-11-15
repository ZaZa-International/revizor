"""Shared test fixtures.

Integration/API tests run against REAL PostgreSQL+PostGIS and Redis
(docker compose services), never SQLite. A dedicated database
`mgts_infra_test` is created and migrated automatically.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

_BASE_DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://mgts:mgts@localhost:5432/mgts_infra"
)
_parsed = urlparse(_BASE_DB_URL)
TEST_DB_NAME = "mgts_infra_test"
TEST_DB_URL = urlunparse(_parsed._replace(path=f"/{TEST_DB_NAME}"))
SERVER_DB_URL = urlunparse(_parsed._replace(path="/postgres"))

os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ["STORAGE_BACKEND"] = "local"
os.environ.setdefault("STORAGE_LOCAL_PATH", tempfile.mkdtemp(prefix="mgts-test-storage-"))
os.environ["APP_ENV"] = "test"
os.environ["QUEUE_MODE"] = "inline"
os.environ["ML_PROVIDER"] = "mock"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["BOOTSTRAP_ADMIN_USERNAME"] = "admin"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "admin-test-password"
os.environ["RATE_LIMIT_LOGIN_PER_MINUTE"] = "10000"
os.environ["RATE_LIMIT_UPLOAD_PER_MINUTE"] = "10000"
os.environ["LOG_FORMAT"] = "console"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["PROCESSING_FRAME_INTERVAL_SECONDS"] = "1.0"

from app.config import Settings, get_settings  # noqa: E402
from app.infrastructure.database.session import Database  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="session")
async def prepare_database(settings: Settings) -> AsyncIterator[None]:
    import asyncpg
    from redis.asyncio import Redis

    parsed = urlparse(TEST_DB_URL.replace("+asyncpg", ""))
    conn = await asyncpg.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        user=parsed.username or "mgts",
        password=parsed.password or "mgts",
        database="postgres",
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await conn.close()

    result = subprocess.run(  # noqa: ASYNC221
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed:\n{result.stdout}\n{result.stderr}")

    redis = Redis.from_url(os.environ["REDIS_URL"])
    await redis.flushdb()
    await redis.aclose()
    yield


@pytest.fixture(scope="session")
async def database(settings: Settings, prepare_database: None) -> AsyncIterator[Database]:
    db = Database(settings)
    yield db
    await db.dispose()


@pytest.fixture(autouse=True)
async def clean_tables(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    if request.node.get_closest_marker("unit"):
        yield
        return
    database = request.getfixturevalue("database")
    request.getfixturevalue("prepare_database")
    from sqlalchemy import text

    async with database.session() as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                        "AND tablename NOT IN ('alembic_version', 'spatial_ref_sys')"
                    )
                )
            )
            .scalars()
            .all()
        )
        if rows:
            tables = ", ".join(f'"{t}"' for t in rows)
            await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
            await session.commit()
    yield


@pytest.fixture
async def app(clean_tables: None, settings: Settings):
    from app.main import create_app

    application = create_app()
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app) -> AsyncIterator:
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def _login(client, username: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin_headers(client) -> dict[str, str]:
    return await _login(client, "admin", "admin-test-password")


async def _create_user_headers(
    client, database: Database, username: str, role: str
) -> dict[str, str]:
    from app.core.security import hash_password
    from app.domain.enums import UserRole
    from app.infrastructure.database.models.user import User

    async with database.session() as session:
        session.add(
            User(
                username=username,
                password_hash=hash_password("user-test-password"),
                role=UserRole(role),
                is_active=True,
            )
        )
        await session.commit()
    return await _login(client, username, "user-test-password")


@pytest.fixture
async def operator_headers(client, database: Database) -> dict[str, str]:
    return await _create_user_headers(client, database, "operator1", "OPERATOR")


@pytest.fixture
async def viewer_headers(client, database: Database) -> dict[str, str]:
    return await _create_user_headers(client, database, "viewer1", "VIEWER")
