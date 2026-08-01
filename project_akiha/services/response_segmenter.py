"""Conservatively segment streamed canonical assistant text for speech."""

from __future__ import annotations

from project_akiha.core.voice_session import CanonicalResponseSegment

_JAPANESE_SENTENCE_ENDINGS = frozenset("。！？")
_LATIN_SENTENCE_ENDINGS = frozenset(".!?")
_TRAILING_CLOSERS = frozenset("\"')]}\u2019\u201d\u300d\u300f\u3011\uff09")
_CLAUSE_ENDINGS = frozenset(",;:\u3001\uff0c\uff1b\uff1a")
_COMMON_ABBREVIATIONS = frozenset(
    {
        "dr.",
        "e.g.",
        "etc.",
        "i.e.",
        "jr.",
        "mr.",
        "mrs.",
        "ms.",
        "prof.",
        "sr.",
        "st.",
        "vs.",
    }
)


class StableResponseSegmenter:
    """Turn provider deltas into ordered, immutable canonical text spans."""

    def __init__(
        self,
        response_id: str,
        *,
        minimum_clause_chars: int = 96,
        clause_release_chars: int = 32,
        maximum_segment_chars: int = 320,
    ) -> None:
        if not response_id.strip():
            raise ValueError("response ID cannot be empty.")
        if minimum_clause_chars < 32:
            raise ValueError("minimum clause length cannot be less than 32.")
        if clause_release_chars < 8:
            raise ValueError("clause release length cannot be less than 8.")
        if maximum_segment_chars < minimum_clause_chars:
            raise ValueError(
                "maximum segment length cannot be less than the clause length."
            )

        self._response_id = response_id
        self._minimum_clause_chars = minimum_clause_chars
        self._clause_release_chars = clause_release_chars
        self._maximum_segment_chars = maximum_segment_chars
        self._buffer = ""
        self._next_segment_index = 0
        self._finished = False

    @property
    def pending_text_length(self) -> int:
        """Return buffered character count without exposing response content."""
        return len(self._buffer)

    def push(self, delta: str) -> tuple[CanonicalResponseSegment, ...]:
        """Accept one canonical provider delta and emit newly stable spans."""
        if self._finished:
            raise RuntimeError("cannot append to a finished response segmenter.")
        if not isinstance(delta, str):
            raise TypeError("response delta must be text.")
        if not delta:
            return ()

        self._buffer += delta
        emitted: list[CanonicalResponseSegment] = []
        while boundary := self._next_stable_boundary():
            segment = self._take(boundary, is_final=False)
            if segment is not None:
                emitted.append(segment)
        return tuple(emitted)

    def finish(self) -> tuple[CanonicalResponseSegment, ...]:
        """Flush the final non-empty span and reject future provider deltas."""
        if self._finished:
            return ()
        self._finished = True
        segment = self._take(len(self._buffer), is_final=True)
        return (segment,) if segment is not None else ()

    def cancel(self) -> None:
        """Discard unstable text and reject future provider deltas."""
        self._buffer = ""
        self._finished = True

    def _next_stable_boundary(self) -> int | None:
        sentence_boundaries = _sentence_boundaries(self._buffer)
        if sentence_boundaries:
            first = sentence_boundaries[0]
            if self._buffer[first:].strip():
                return first
            return None

        clause_boundary = _conservative_clause_boundary(
            self._buffer,
            minimum_prefix_chars=self._minimum_clause_chars,
            minimum_suffix_chars=self._clause_release_chars,
        )
        if clause_boundary is not None:
            return clause_boundary

        if len(self._buffer) <= (
            self._maximum_segment_chars + self._clause_release_chars
        ):
            return None
        return _bounded_word_boundary(self._buffer, self._maximum_segment_chars)

    def _take(
        self,
        boundary: int,
        *,
        is_final: bool,
    ) -> CanonicalResponseSegment | None:
        canonical_text = self._buffer[:boundary].strip()
        self._buffer = self._buffer[boundary:].lstrip()
        if not canonical_text:
            return None
        segment = CanonicalResponseSegment(
            response_id=self._response_id,
            segment_index=self._next_segment_index,
            canonical_text=canonical_text,
            is_final=is_final,
        )
        self._next_segment_index += 1
        return segment


def _sentence_boundaries(text: str) -> tuple[int, ...]:
    boundaries: list[int] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character not in _JAPANESE_SENTENCE_ENDINGS | _LATIN_SENTENCE_ENDINGS:
            index += 1
            continue

        if character == "." and not _is_latin_period_boundary(text, index):
            index += 1
            continue

        end = index + 1
        while end < len(text) and text[end] in (
            _JAPANESE_SENTENCE_ENDINGS | _LATIN_SENTENCE_ENDINGS
        ):
            end += 1
        while end < len(text) and text[end] in _TRAILING_CLOSERS:
            end += 1

        if character in _JAPANESE_SENTENCE_ENDINGS:
            boundaries.append(end)
        elif end == len(text) or text[end].isspace():
            boundaries.append(end)
        index = end
    return tuple(boundaries)


def _is_latin_period_boundary(text: str, index: int) -> bool:
    previous = text[index - 1] if index else ""
    following = text[index + 1] if index + 1 < len(text) else ""
    if previous.isdigit() and following.isdigit():
        return False

    token_start = index
    while token_start > 0 and not text[token_start - 1].isspace():
        token_start -= 1
    token = text[token_start : index + 1].casefold()
    if token in _COMMON_ABBREVIATIONS:
        return False
    if len(token) == 2 and token[0].isalpha():
        return False
    if token[:-1].isdigit():
        return False
    return True


def _conservative_clause_boundary(
    text: str,
    *,
    minimum_prefix_chars: int,
    minimum_suffix_chars: int,
) -> int | None:
    maximum_index = len(text) - minimum_suffix_chars
    for index, character in enumerate(text):
        boundary = index + 1
        if boundary < minimum_prefix_chars or boundary > maximum_index:
            continue
        if character in _CLAUSE_ENDINGS:
            return boundary
    return None


def _bounded_word_boundary(text: str, maximum_segment_chars: int) -> int | None:
    boundary = maximum_segment_chars
    while boundary > 0 and not text[boundary - 1].isspace():
        boundary -= 1
    if boundary <= 0:
        return maximum_segment_chars
    return boundary
