"""Pure deduplication decision policy.

Combines spatial distance, asset type, temporal context, route/tracking
context and (optionally) visual/embedding similarity into a transparent
score. The application layer feeds candidate evidence from PostGIS; this
module contains no I/O. Ambiguous candidates are NEVER auto-merged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import DeduplicationResult

WEIGHTS = {
    "spatial": 0.55,
    "type": 0.20,
    "temporal": 0.05,
    "context": 0.15,
    "visual": 0.05,
}
NEUTRAL_VISUAL_SCORE = 0.5
AMBIGUITY_MARGIN = 0.10


@dataclass(frozen=True)
class CandidateEvidence:
    asset_id: str
    asset_type: str
    distance_m: float
    hours_since_last_observation: float | None
    same_route: bool = False
    same_tracking_id: bool = False
    visual_similarity: float | None = None
    embedding_similarity: float | None = None


@dataclass(frozen=True)
class DeduplicationConfig:
    radius_m: float = 15.0
    match_threshold: float = 0.70
    possible_threshold: float = 0.45
    time_window_hours: float = 2.0


@dataclass(frozen=True)
class DeduplicationDecision:
    result: DeduplicationResult
    asset_id: str | None
    score: float
    explanation: dict[str, object] = field(default_factory=dict)


def _spatial_score(distance_m: float, radius_m: float) -> float:
    if distance_m > radius_m:
        return 0.0
    return max(0.0, 1.0 - distance_m / radius_m)


def _temporal_score(hours: float | None, window_hours: float) -> float:
    if hours is None:
        return NEUTRAL_VISUAL_SCORE
    if hours <= window_hours:
        return 1.0
    return max(0.0, 1.0 - (hours - window_hours) / 24.0)


def _context_score(evidence: CandidateEvidence) -> float:
    if evidence.same_tracking_id:
        return 1.0
    if evidence.same_route:
        return 0.7
    return 0.3


def _visual_score(evidence: CandidateEvidence) -> float:
    if evidence.embedding_similarity is not None:
        return max(0.0, min(1.0, evidence.embedding_similarity))
    if evidence.visual_similarity is not None:
        return max(0.0, min(1.0, evidence.visual_similarity))
    return NEUTRAL_VISUAL_SCORE


def score_candidate(
    evidence: CandidateEvidence, *, object_type: str, radius_m: float, time_window_hours: float
) -> tuple[float, dict[str, float]]:
    factors = {
        "spatial": _spatial_score(evidence.distance_m, radius_m),
        "type": 1.0 if evidence.asset_type == object_type else 0.0,
        "temporal": _temporal_score(evidence.hours_since_last_observation, time_window_hours),
        "context": _context_score(evidence),
        "visual": _visual_score(evidence),
    }
    score = sum(WEIGHTS[name] * value for name, value in factors.items())
    return round(score, 4), factors


def decide(
    candidates: list[CandidateEvidence],
    *,
    object_type: str,
    config: DeduplicationConfig,
) -> DeduplicationDecision:
    if not candidates:
        return DeduplicationDecision(
            DeduplicationResult.NEW_ASSET, None, 0.0, {"reason": "no_candidates_in_radius"}
        )

    scored: list[tuple[CandidateEvidence, float, dict[str, float]]] = []
    for evidence in candidates:
        if evidence.asset_type != object_type:
            continue
        if evidence.distance_m > config.radius_m:
            continue
        score, factors = score_candidate(
            evidence,
            object_type=object_type,
            radius_m=config.radius_m,
            time_window_hours=config.time_window_hours,
        )
        scored.append((evidence, score, factors))

    if not scored:
        return DeduplicationDecision(
            DeduplicationResult.NEW_ASSET,
            None,
            0.0,
            {"reason": "no_candidates_same_type_in_radius", "candidates_seen": len(candidates)},
        )

    scored.sort(key=lambda item: item[1], reverse=True)
    best_evidence, best_score, best_factors = scored[0]
    explanation: dict[str, object] = {
        "policy": "weighted-v1",
        "weights": WEIGHTS,
        "config": {
            "radius_m": config.radius_m,
            "match_threshold": config.match_threshold,
            "possible_threshold": config.possible_threshold,
        },
        "best_factors": best_factors,
        "candidates": [
            {"asset_id": ev.asset_id, "score": sc, "distance_m": ev.distance_m}
            for ev, sc, _ in scored[:5]
        ],
    }

    if best_score >= config.match_threshold:
        if (
            len(scored) > 1
            and scored[1][1] >= config.match_threshold
            and best_score - scored[1][1] < AMBIGUITY_MARGIN
        ):
            explanation["reason"] = "multiple_strong_candidates"
            return DeduplicationDecision(
                DeduplicationResult.AMBIGUOUS, None, best_score, explanation
            )
        explanation["reason"] = "score_above_match_threshold"
        return DeduplicationDecision(
            DeduplicationResult.MATCHED, best_evidence.asset_id, best_score, explanation
        )

    if best_score >= config.possible_threshold:
        explanation["reason"] = "score_in_possible_band"
        return DeduplicationDecision(
            DeduplicationResult.POSSIBLE_MATCH, best_evidence.asset_id, best_score, explanation
        )

    explanation["reason"] = "score_below_possible_threshold"
    return DeduplicationDecision(DeduplicationResult.NEW_ASSET, None, best_score, explanation)
