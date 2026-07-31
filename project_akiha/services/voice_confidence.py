"""Language-neutral confidence policy for final speech transcripts."""

from __future__ import annotations

_LOW_CONFIDENCE_THRESHOLD = 0.30
_HIGH_CONFIDENCE_THRESHOLD = 0.70


def voice_confidence_level(confidence: float | None) -> str | None:
    """Convert optional provider confidence to a stable qualitative band."""
    if confidence is None:
        return None
    if confidence < _LOW_CONFIDENCE_THRESHOLD:
        return "low"
    if confidence < _HIGH_CONFIDENCE_THRESHOLD:
        return "medium"
    return "high"


def transcript_requires_review(confidence: float | None) -> bool:
    """Require user confirmation only when a provider reports low confidence."""
    return voice_confidence_level(confidence) == "low"
