"""Job queue abstraction: RQ in production, inline execution for tests/dev."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable


@runtime_checkable
class JobQueue(Protocol):
    async def enqueue_processing(self, job_id: uuid.UUID) -> str | None: ...

    async def queue_length(self) -> int: ...

    async def close(self) -> None: ...
