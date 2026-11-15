import pytest
from app.domain.enums import JobStatus
from app.domain.processing.state_machine import (
    InvalidTransitionError,
    assert_transition,
    can_transition,
    is_cancellable,
    is_retryable,
)

pytestmark = pytest.mark.unit


def test_happy_path_transitions():
    assert can_transition(JobStatus.PENDING, JobStatus.QUEUED)
    assert can_transition(JobStatus.QUEUED, JobStatus.PROCESSING)
    assert can_transition(JobStatus.PROCESSING, JobStatus.COMPLETED)
    assert can_transition(JobStatus.PROCESSING, JobStatus.PARTIALLY_COMPLETED)


def test_completed_is_terminal():
    for target in JobStatus:
        assert not can_transition(JobStatus.COMPLETED, target)


def test_retry_paths():
    assert can_transition(JobStatus.FAILED, JobStatus.QUEUED)
    assert can_transition(JobStatus.PARTIALLY_COMPLETED, JobStatus.QUEUED)
    assert can_transition(JobStatus.CANCELLED, JobStatus.QUEUED)
    assert not can_transition(JobStatus.COMPLETED, JobStatus.QUEUED)


def test_invalid_transition_raises():
    with pytest.raises(InvalidTransitionError):
        assert_transition(JobStatus.PENDING, JobStatus.COMPLETED)
    with pytest.raises(InvalidTransitionError):
        assert_transition(JobStatus.COMPLETED, JobStatus.PROCESSING)


def test_retryable_and_cancellable_sets():
    assert is_retryable(JobStatus.FAILED)
    assert is_retryable(JobStatus.PARTIALLY_COMPLETED)
    assert not is_retryable(JobStatus.PROCESSING)
    assert is_cancellable(JobStatus.QUEUED)
    assert is_cancellable(JobStatus.PROCESSING)
    assert not is_cancellable(JobStatus.COMPLETED)
    assert not is_cancellable(JobStatus.FAILED)
