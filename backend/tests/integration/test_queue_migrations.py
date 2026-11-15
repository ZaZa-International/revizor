"""RQ enqueue against real Redis; migration state on real PostGIS."""

from __future__ import annotations

import subprocess
import sys

import pytest
from app.config import Settings
from app.infrastructure.queue.rq_queue import PROCESSING_TASK, RQJobQueue
from redis import Redis
from rq import Queue

pytestmark = pytest.mark.integration


async def test_rq_enqueue_registers_task():
    import uuid

    settings = Settings(queue_mode="rq")
    queue = RQJobQueue(settings)
    job_id = uuid.uuid4()
    try:
        rq_id = await queue.enqueue_processing(job_id)
        assert rq_id
        assert await queue.queue_length() >= 1
        connection = Redis.from_url(settings.redis_url)
        rq_job = Queue(settings.rq_queue_name, connection=connection).fetch_job(rq_id)
        assert rq_job is not None
        assert rq_job.func_name == PROCESSING_TASK
        assert rq_job.args == (str(job_id),)
        assert rq_job.retries_left == settings.rq_retry_max
        connection.close()
    finally:
        connection = Redis.from_url(settings.redis_url)
        Queue(settings.rq_queue_name, connection=connection).empty()
        connection.close()
        await queue.close()


async def test_migration_head_and_postgis(prepare_database, database):
    from sqlalchemy import text

    async with database.session() as conn:
        version = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
        assert version == "0001_initial"
        ext = (
            await conn.execute(text("SELECT extname FROM pg_extension WHERE extname='postgis'"))
        ).scalar_one()
        assert ext == "postgis"
        gist = (
            (
                await conn.execute(
                    text(
                        "SELECT indexname FROM pg_indexes WHERE indexdef ILIKE '%gist%' "
                        "AND tablename IN ('assets','observations','routes')"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(gist) >= 3


async def test_migration_roundtrip(prepare_database, database):
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parents[2]  # noqa: ASYNC240
    for args in (["downgrade", "base"], ["upgrade", "head"]):
        result = subprocess.run(  # noqa: ASYNC221
            [sys.executable, "-m", "alembic", *args],
            cwd=backend_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, result.stderr
    await database.engine.dispose()
