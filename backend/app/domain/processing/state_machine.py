"""ProcessingJob state machine: explicit, validated transitions."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.enums import JobStatus

_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.PENDING: frozenset({JobStatus.QUEUED, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.QUEUED: frozenset({JobStatus.PROCESSING, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.PROCESSING: frozenset(
        {
            JobStatus.COMPLETED,
            JobStatus.PARTIALLY_COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.QUEUED,
        }
    ),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.PARTIALLY_COMPLETED: frozenset(
        {JobStatus.QUEUED, JobStatus.CANCELLED, JobStatus.PROCESSING}
    ),
    JobStatus.FAILED: frozenset({JobStatus.QUEUED, JobStatus.CANCELLED, JobStatus.PROCESSING}),
    JobStatus.CANCELLED: frozenset({JobStatus.QUEUED}),
}

RETRYABLE_STATUSES = frozenset(
    {JobStatus.FAILED, JobStatus.PARTIALLY_COMPLETED, JobStatus.CANCELLED}
)
CANCELLABLE_STATUSES = frozenset({JobStatus.PENDING, JobStatus.QUEUED, JobStatus.PROCESSING})
TERMINAL_STATUSES = frozenset({JobStatus.COMPLETED})


class InvalidTransitionError(ValueError):
    def __init__(self, current: JobStatus, target: JobStatus) -> None:
        super().__init__(f"Invalid job transition {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: JobStatus, target: JobStatus) -> bool:
    return target in _TRANSITIONS[current]


def assert_transition(current: JobStatus, target: JobStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)


def is_retryable(status: JobStatus) -> bool:
    return status in RETRYABLE_STATUSES


def is_cancellable(status: JobStatus) -> bool:
    return status in CANCELLABLE_STATUSES


def is_stale_processing(status: JobStatus, updated_at: datetime, threshold_seconds: int) -> bool:
    """True when a PROCESSING job has not reported progress for longer than the
    threshold (rq_job_timeout + grace). Only such jobs may go PROCESSING->QUEUED;
    fresh PROCESSING jobs are owned by a live executor (fenced by advisory lock).
    """
    if status != JobStatus.PROCESSING:
        return False
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return (datetime.now(UTC) - updated_at).total_seconds() > threshold_seconds
