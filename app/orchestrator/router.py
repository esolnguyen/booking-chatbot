"""Confidence scoring and routing logic."""

from app.models.option import BookingOption
from app.config import settings


def compute_confidence(
    option: BookingOption,
    evidence_ok: float,
    freshness_ok: float,
    margin: float,
) -> float:
    """Weighted confidence score per the design doc formula."""
    score = (
        0.35 * float(option.policy_compliant)
        + 0.25 * float(option.inventory_available)
        + 0.20 * evidence_ok
        + 0.10 * freshness_ok
        + 0.10 * margin
    )
    return round(score, 3)


def determine_route(confidence: float) -> str:
    """Route based on confidence thresholds."""
    if confidence >= settings.auto_suggest_threshold:
        return "auto_suggest"
    elif confidence < settings.human_review_threshold:
        return "human_review"
    return "suggest_with_caution"
