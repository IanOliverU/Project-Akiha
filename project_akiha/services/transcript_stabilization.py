"""Language-neutral stabilization for replaceable speech transcript previews."""

from __future__ import annotations

from difflib import SequenceMatcher


class PartialTranscriptStabilizer:
    """Keep rolling STT previews responsive without visible regressions."""

    def __init__(self) -> None:
        self._presented = ""
        self._pending_revision = ""

    def reset(self) -> None:
        """Forget preview state at the boundary of one recording."""
        self._presented = ""
        self._pending_revision = ""

    def observe(self, text: str) -> str | None:
        """Return a stable preview update, or suppress an unstable revision."""
        candidate = " ".join(text.split())
        if not candidate:
            return None
        if not self._presented:
            return self._accept(candidate)

        presented_key = self._presented.casefold()
        candidate_key = candidate.casefold()
        if candidate_key == presented_key:
            self._pending_revision = ""
            return None
        if presented_key.startswith(candidate_key):
            self._pending_revision = ""
            return None
        if _is_related_growth(presented_key, candidate_key):
            return self._accept(candidate)

        if self._pending_revision and (
            candidate_key == self._pending_revision.casefold()
            or _is_related_growth(
                self._pending_revision.casefold(),
                candidate_key,
            )
        ):
            return self._accept(candidate)

        self._pending_revision = candidate
        return None

    def _accept(self, text: str) -> str:
        self._presented = text
        self._pending_revision = ""
        return text


def _is_related_growth(previous: str, candidate: str) -> bool:
    if len(candidate) <= len(previous):
        return False
    if candidate.startswith(previous):
        return True

    similarity = SequenceMatcher(None, previous, candidate, autojunk=False).ratio()
    prefix_length = 0
    for previous_character, candidate_character in zip(
        previous,
        candidate,
        strict=False,
    ):
        if previous_character != candidate_character:
            break
        prefix_length += 1
    prefix_ratio = prefix_length / max(1, len(previous))
    return similarity >= 0.72 or prefix_ratio >= 0.55
