import pytest
from app.domain.observations.condition import (
    CANONICAL_CONDITIONS,
    default_severity_for_condition,
    defect_type_for_condition,
    normalize_condition,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("damaged_cover", "damaged_cover"),
        ("broken-cover", "damaged_cover"),
        ("BROKEN COVER", "damaged_cover"),
        ("open_door", "door_open"),
        ("no_cover", "missing_cover"),
        ("sagging", "cable_sag"),
        ("ok", "ok"),
        ("normal", "ok"),
        (None, "unknown"),
        ("totally-new-class", "unknown"),
        ("", "unknown"),
    ],
)
def test_normalize(raw, expected):
    assert normalize_condition(raw) == expected


def test_all_aliases_map_to_canonical():
    from app.domain.observations.condition import CONDITION_ALIASES

    assert set(CONDITION_ALIASES.values()) <= CANONICAL_CONDITIONS


def test_default_severity_scale():
    assert default_severity_for_condition("missing_cover") == 5
    assert default_severity_for_condition("ok") == 1
    assert 1 <= default_severity_for_condition("never-seen") <= 5


def test_defect_mapping():
    assert defect_type_for_condition("missing_cover") == "missing_cover"
    assert defect_type_for_condition("door_open") == "cabinet_door_open"
    assert defect_type_for_condition("ok") is None
    assert defect_type_for_condition("unknown") is None
