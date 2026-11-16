"""One-shot migration runner with a PostgreSQL advisory lock (OPS-1).

Serializes concurrent ``alembic upgrade head`` runs (multi-replica backend
start, parallel deploy jobs) behind ``pg_advisory_lock``. Reads DATABASE_URL
(``postgresql+asyncpg://...``), runs alembic as a subprocess, always releases
the lock, and propagates the alembic exit code.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

import asyncpg

LOCK_KEY = 728390123
SCRIPT_DIR = Path(__file__).resolve().parent

logger = logging.getLogger("migrate")


def _asyncpg_dsn(url: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


def _alembic_upgrade() -> int:
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=True,
            cwd=SCRIPT_DIR,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("alembic upgrade head failed with exit code %d", exc.returncode)
        return exc.returncode
    return 0


async def _run() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        logger.error("DATABASE_URL is not set")
        return 1

    connection = await asyncpg.connect(_asyncpg_dsn(url))
    try:
        logger.info("acquiring advisory lock %d", LOCK_KEY)
        await connection.execute("SELECT pg_advisory_lock($1)", LOCK_KEY)
        logger.info("running alembic upgrade head")
        returncode = await asyncio.to_thread(_alembic_upgrade)
        if returncode == 0:
            logger.info("migrations applied")
        return returncode
    finally:
        try:
            await connection.execute("SELECT pg_advisory_unlock($1)", LOCK_KEY)
        finally:
            await connection.close()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        return asyncio.run(_run())
    except Exception:
        logger.exception("migration run failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
