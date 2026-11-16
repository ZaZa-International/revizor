"""RQ worker entrypoint: python -m app.workers.worker

Metrics: RQ forks a work-horse per job, so pipeline counters are incremented
in child processes. prometheus_client multiprocess mode (mmap files in a
per-run temp dir) aggregates them; the parent serves the summed registry.
The env var MUST be set before prometheus_client is imported anywhere.
"""

from __future__ import annotations

import os
import tempfile

os.environ["PROMETHEUS_MULTIPROC_DIR"] = tempfile.mkdtemp(prefix="mgts-worker-metrics-")

import asyncio
import threading
import time
import uuid

from redis import Redis
from rq import Worker

from app.application.use_cases.processing.recovery import sweep_stale_jobs
from app.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.infrastructure.database.session import Database

_SWEEP_INTERVAL_SECONDS = 600


def _sweep_once(settings: Settings, connection: Redis | None = None) -> list[uuid.UUID]:
    async def _run() -> list[uuid.UUID]:
        database = Database(settings, null_pool=True)
        try:
            return await sweep_stale_jobs(database, settings, redis_connection=connection)
        finally:
            await database.dispose()

    return asyncio.run(_run())


def _sweep_daemon(settings: Settings) -> None:
    logger = get_logger("app.worker.sweeper")
    while True:
        time.sleep(_SWEEP_INTERVAL_SECONDS)
        try:
            recovered = _sweep_once(settings)
            if recovered:
                logger.info(
                    "stale_jobs_swept", count=len(recovered), job_ids=[str(i) for i in recovered]
                )
        except Exception:
            logger.exception("stale_job_sweep_failed")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(settings.processing_max_image_pixels))
    logger = get_logger("app.worker")

    from prometheus_client import CollectorRegistry, multiprocess, start_http_server

    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    try:
        start_http_server(settings.worker_metrics_port, registry=registry)
        logger.info("worker_metrics_server_started", port=settings.worker_metrics_port)
    except OSError as exc:
        logger.warning("worker_metrics_server_failed", error=str(exc))

    connection = Redis.from_url(settings.redis_url)
    try:
        recovered = _sweep_once(settings, connection)
        logger.info("worker_startup_sweep", recovered=len(recovered))
    except Exception:
        logger.exception("worker_startup_sweep_failed")

    threading.Thread(
        target=_sweep_daemon, args=(settings,), daemon=True, name="stale-sweeper"
    ).start()

    worker = Worker([settings.rq_queue_name], connection=connection)
    logger.info("worker_start", queue=settings.rq_queue_name)
    worker.work(with_scheduler=True, logging_level=settings.log_level)


if __name__ == "__main__":
    main()
