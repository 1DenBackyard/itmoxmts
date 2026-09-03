from __future__ import annotations

from typing import Tuple

from .config import DONENESS_LABELS, TRAFFIC_BY_DONENESS


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def score_finding(probability: float, impact: float) -> float:
    return round(clamp01(probability) * clamp01(impact), 4)


def doneness_from_score(score: float) -> str:
    if score >= 0.75:
        return "well_done"
    if score >= 0.45:
        return "medium"
    if score >= 0.25:
        return "medium_rare"
    return "rare"


def enrich_risk(probability: float, impact: float) -> Tuple[float, str, str]:
    """Return score, doneness, traffic_light."""
    score = score_finding(probability, impact)
    doneness = doneness_from_score(score)
    return score, doneness, TRAFFIC_BY_DONENESS[doneness]


def doneness_caption(doneness: str) -> str:
    return DONENESS_LABELS.get(doneness, doneness)
