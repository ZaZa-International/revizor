"""Condition class normalization: ML labels -> canonical condition vocabulary."""

from __future__ import annotations

CONDITION_ALIASES: dict[str, str] = {
    "ok": "ok",
    "normal": "ok",
    "intact": "ok",
    "good": "ok",
    "damaged": "damaged",
    "broken": "damaged",
    "damaged_cover": "damaged_cover",
    "broken_cover": "damaged_cover",
    "cover_damaged": "damaged_cover",
    "missing_cover": "missing_cover",
    "cover_missing": "missing_cover",
    "no_cover": "missing_cover",
    "open_door": "door_open",
    "door_open": "door_open",
    "cabinet_open": "door_open",
    "tilted": "tilted",
    "tilt": "tilted",
    "leaning": "tilted",
    "subsided": "subsided",
    "subsidence": "subsided",
    "sag": "cable_sag",
    "cable_sag": "cable_sag",
    "sagging": "cable_sag",
    "cable_break": "cable_break",
    "broken_cable": "cable_break",
    "cut_cable": "cable_break",
}

CANONICAL_CONDITIONS: frozenset[str] = frozenset(set(CONDITION_ALIASES.values()) | {"unknown"})

CONDITION_DEFAULT_SEVERITY: dict[str, int] = {
    "ok": 1,
    "damaged": 3,
    "damaged_cover": 4,
    "missing_cover": 5,
    "door_open": 3,
    "tilted": 4,
    "subsided": 4,
    "cable_sag": 3,
    "cable_break": 5,
    "unknown": 2,
}

CONDITION_DEFECT_MAP: dict[str, str] = {
    "damaged_cover": "damaged_cover",
    "missing_cover": "missing_cover",
    "door_open": "cabinet_door_open",
    "tilted": "pole_tilt",
    "subsided": "well_subsidence",
    "cable_sag": "cable_sag",
    "cable_break": "cable_break",
    "damaged": "other",
}


def normalize_condition(raw: str | None) -> str:
    if raw is None:
        return "unknown"
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return CONDITION_ALIASES.get(key, "unknown")


def default_severity_for_condition(condition: str) -> int:
    return CONDITION_DEFAULT_SEVERITY.get(condition, 2)


def defect_type_for_condition(condition: str) -> str | None:
    return CONDITION_DEFECT_MAP.get(condition)
