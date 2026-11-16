"""Explicit defect status transition matrix (operator PATCH semantics).

REJECTED is terminal via API: a rejected defect can only be revived through
the append-only review workflow, not by a direct status edit.
RESOLVED -> OPEN is an explicit reopen (resolved_at is cleared).
"""

from __future__ import annotations

from app.domain.enums import DefectStatus

_TRANSITIONS: dict[DefectStatus, frozenset[DefectStatus]] = {
    DefectStatus.OPEN: frozenset(
        {
            DefectStatus.CONFIRMED,
            DefectStatus.IN_PROGRESS,
            DefectStatus.RESOLVED,
            DefectStatus.REJECTED,
        }
    ),
    DefectStatus.CONFIRMED: frozenset({DefectStatus.IN_PROGRESS, DefectStatus.RESOLVED}),
    DefectStatus.IN_PROGRESS: frozenset({DefectStatus.CONFIRMED, DefectStatus.RESOLVED}),
    DefectStatus.RESOLVED: frozenset({DefectStatus.OPEN}),
    DefectStatus.REJECTED: frozenset(),
}


class InvalidDefectTransitionError(ValueError):
    def __init__(self, current: DefectStatus, target: DefectStatus) -> None:
        super().__init__(f"Invalid defect transition {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition_defect(current: DefectStatus, target: DefectStatus) -> bool:
    return target in _TRANSITIONS[current]


def assert_defect_transition(current: DefectStatus, target: DefectStatus) -> None:
    if current != target and not can_transition_defect(current, target):
        raise InvalidDefectTransitionError(current, target)
