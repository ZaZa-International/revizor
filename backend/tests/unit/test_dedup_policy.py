import pytest
from app.domain.deduplication.policy import CandidateEvidence, DeduplicationConfig, decide
from app.domain.enums import DeduplicationResult

pytestmark = pytest.mark.unit

CONFIG = DeduplicationConfig(radius_m=15, match_threshold=0.75, possible_threshold=0.45)


def ev(asset_id="a1", distance=2.0, hours=0.5, **kwargs):
    return CandidateEvidence(
        asset_id=asset_id,
        asset_type=kwargs.pop("asset_type", "telecom_well"),
        distance_m=distance,
        hours_since_last_observation=hours,
        **kwargs,
    )


def test_no_candidates_means_new_asset():
    decision = decide([], object_type="telecom_well", config=CONFIG)
    assert decision.result == DeduplicationResult.NEW_ASSET
    assert decision.asset_id is None
    assert decision.explanation["reason"] == "no_candidates_in_radius"


def test_close_same_type_recent_is_matched():
    decision = decide([ev(distance=1.0, hours=0.1)], object_type="telecom_well", config=CONFIG)
    assert decision.result == DeduplicationResult.MATCHED
    assert decision.asset_id == "a1"
    assert decision.score >= CONFIG.match_threshold
    assert "best_factors" in decision.explanation


def test_different_type_never_matches():
    decision = decide(
        [ev(asset_type="pole", distance=1.0)], object_type="telecom_well", config=CONFIG
    )
    assert decision.result == DeduplicationResult.NEW_ASSET
    assert decision.asset_id is None


def test_far_distance_not_matched():
    decision = decide([ev(distance=50.0)], object_type="telecom_well", config=CONFIG)
    assert decision.result == DeduplicationResult.NEW_ASSET


def test_borderline_distance_possible_match():
    decision = decide([ev(distance=8.0, hours=6.0)], object_type="telecom_well", config=CONFIG)
    assert decision.result == DeduplicationResult.POSSIBLE_MATCH
    assert decision.asset_id == "a1"
    assert CONFIG.possible_threshold <= decision.score < CONFIG.match_threshold


def test_two_strong_candidates_ambiguous_not_merged():
    decision = decide(
        [ev(asset_id="a1", distance=2.0), ev(asset_id="a2", distance=2.5)],
        object_type="telecom_well",
        config=CONFIG,
    )
    assert decision.result == DeduplicationResult.AMBIGUOUS
    assert decision.asset_id is None
    assert decision.explanation["reason"] == "multiple_strong_candidates"


def test_tracking_boosts_score():
    without = decide([ev(distance=8.0, hours=20.0)], object_type="telecom_well", config=CONFIG)
    with_track = decide(
        [ev(distance=8.0, hours=20.0, same_tracking_id=True)],
        object_type="telecom_well",
        config=CONFIG,
    )
    assert with_track.score > without.score


def test_embedding_similarity_used_when_present():
    high = decide(
        [ev(distance=6.0, hours=10.0, embedding_similarity=0.95)],
        object_type="telecom_well",
        config=CONFIG,
    )
    low = decide(
        [ev(distance=6.0, hours=10.0, embedding_similarity=0.05)],
        object_type="telecom_well",
        config=CONFIG,
    )
    assert high.score > low.score


def test_explanation_contains_candidates_and_weights():
    decision = decide([ev(distance=3.0)], object_type="telecom_well", config=CONFIG)
    assert decision.explanation["weights"]["spatial"] == 0.55
    assert decision.explanation["candidates"][0]["asset_id"] == "a1"


def test_old_observation_decays_temporal_score():
    recent = decide([ev(hours=0.5, distance=5.0)], object_type="telecom_well", config=CONFIG)
    old = decide([ev(hours=100.0, distance=5.0)], object_type="telecom_well", config=CONFIG)
    assert recent.score > old.score
