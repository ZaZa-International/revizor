import pytest
from app.domain.enums import DeduplicationResult, PriorityBand, ReviewDecision
from app.domain.risk.scoring import RiskInput, RiskPolicy, assess_risk

pytestmark = pytest.mark.unit

POLICY = RiskPolicy(version="1.0", high_threshold=70, medium_threshold=40)


def test_high_severity_high_confidence_gives_high_priority():
    result = assess_risk(
        RiskInput(
            "telecom_well", severity=5, confidence=0.95, review_decision=ReviewDecision.CONFIRMED
        ),
        POLICY,
    )
    assert result.priority == pytest.approx(97.5, abs=0.1)
    assert result.band == PriorityBand.HIGH_PRIORITY
    assert result.policy_version == "1.0"
    assert result.factors["impact_factor"] == 1.0


def test_low_confidence_does_not_zero_priority():
    result = assess_risk(
        RiskInput(
            "telecom_well", severity=5, confidence=0.1, review_decision=ReviewDecision.CONFIRMED
        ),
        POLICY,
    )
    assert result.priority > 40
    assert result.factors["confidence_factor"] == pytest.approx(0.55)


def test_unreviewed_low_confidence_routes_to_needs_review():
    result = assess_risk(RiskInput("telecom_well", severity=5, confidence=0.3), POLICY)
    assert result.band == PriorityBand.NEEDS_REVIEW


def test_unknown_severity_routes_to_needs_review():
    result = assess_risk(RiskInput("pole", severity=None, confidence=0.9), POLICY)
    assert result.band == PriorityBand.NEEDS_REVIEW
    assert result.factors["severity_known"] is False


def test_ambiguous_dedup_routes_to_needs_review():
    result = assess_risk(
        RiskInput(
            "telecom_well",
            severity=4,
            confidence=0.9,
            deduplication_result=DeduplicationResult.AMBIGUOUS,
        ),
        POLICY,
    )
    assert result.band == PriorityBand.NEEDS_REVIEW


def test_manual_override_wins_over_computed():
    result = assess_risk(
        RiskInput("telecom_well", severity=1, confidence=0.9, manual_override=88.0),
        POLICY,
    )
    assert result.priority == 88.0
    assert result.band == PriorityBand.HIGH_PRIORITY
    assert result.factors["manual_override"] == 88.0


def test_rejected_prediction_gets_zero_priority():
    result = assess_risk(
        RiskInput(
            "telecom_well", severity=5, confidence=0.99, review_decision=ReviewDecision.REJECTED
        ),
        POLICY,
    )
    assert result.priority == 0.0
    assert result.band == PriorityBand.LOW_PRIORITY


def test_impact_factor_scales_priority():
    well = assess_risk(
        RiskInput(
            "telecom_well", severity=4, confidence=0.9, review_decision=ReviewDecision.CONFIRMED
        ),
        POLICY,
    )
    cable = assess_risk(
        RiskInput(
            "cable_line", severity=4, confidence=0.9, review_decision=ReviewDecision.CONFIRMED
        ),
        POLICY,
    )
    assert well.priority > cable.priority


def test_medium_and_low_bands():
    medium = assess_risk(
        RiskInput(
            "telecom_cabinet", severity=3, confidence=0.8, review_decision=ReviewDecision.CONFIRMED
        ),
        POLICY,
    )
    low = assess_risk(
        RiskInput("other", severity=1, confidence=0.8, review_decision=ReviewDecision.CONFIRMED),
        POLICY,
    )
    assert medium.band == PriorityBand.MEDIUM_PRIORITY
    assert low.band == PriorityBand.LOW_PRIORITY


@pytest.mark.parametrize("confidence", [-0.1, 1.5])
def test_invalid_confidence_rejected(confidence):
    with pytest.raises(ValueError):
        assess_risk(RiskInput("telecom_well", severity=3, confidence=confidence), POLICY)


@pytest.mark.parametrize("severity", [0, 6])
def test_invalid_severity_rejected(severity):
    with pytest.raises(ValueError):
        assess_risk(RiskInput("telecom_well", severity=severity, confidence=0.9), POLICY)


def test_priority_clamped_to_100():
    result = assess_risk(
        RiskInput(
            "telecom_well", severity=5, confidence=1.0, review_decision=ReviewDecision.CONFIRMED
        ),
        POLICY,
    )
    assert 0 <= result.priority <= 100
