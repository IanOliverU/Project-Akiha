"""Conservative normalization for text produced by speech recognition."""

from __future__ import annotations

import re

_SPEECH_ECHO_WRAPPER_PATTERN = re.compile(
    r"^(?:(?:i\s+heard\s+you\s+say)\s*[,:-]?\s*)+",
    re.IGNORECASE,
)


def strip_speech_echo_wrappers(text: str) -> str:
    """Remove repeated leading STT echo wrappers without rewriting content."""
    normalized = text.strip()
    unwrapped = _SPEECH_ECHO_WRAPPER_PATTERN.sub("", normalized).strip()
    if unwrapped == normalized:
        return normalized
    return unwrapped.strip("\"'").strip()
