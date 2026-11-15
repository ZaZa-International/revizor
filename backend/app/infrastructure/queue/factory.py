from __future__ import annotations

from app.application.interfaces.queue import JobQueue
from app.config import Settings
from app.infrastructure.queue.inline_queue import InlineJobQueue
from app.infrastructure.queue.rq_queue import RQJobQueue


def build_queue(settings: Settings) -> JobQueue:
    if settings.queue_mode == "inline":
        return InlineJobQueue()
    return RQJobQueue(settings)
