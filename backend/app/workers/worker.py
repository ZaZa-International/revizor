"""RQ worker entrypoint: python -m app.workers.worker"""

from __future__ import annotations

from redis import Redis
from rq import Worker

from app.config import get_settings
from app.core.logging import configure_logging, get_logger


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    logger = get_logger("app.worker")
    connection = Redis.from_url(settings.redis_url)
    worker = Worker([settings.rq_queue_name], connection=connection)
    logger.info("worker_start", queue=settings.rq_queue_name)
    worker.work(with_scheduler=True, logging_level=settings.log_level)


if __name__ == "__main__":
    main()
