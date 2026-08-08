"""Conservative Spotify intent recovery from noisy context-bound speech."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from project_akiha.core.actions.registry import (
    SPOTIFY_NEXT_ACTION,
    SPOTIFY_PAUSE_ACTION,
    SPOTIFY_PLAY_ACTION,
    SPOTIFY_PREVIOUS_ACTION,
    SPOTIFY_RESUME_ACTION,
)

_MATCH_THRESHOLD = 0.74
_CLARIFY_THRESHOLD = 0.58
_AMBIGUITY_MARGIN = 0.08
_ACTION_ALIASES = {
    SPOTIFY_PAUSE_ACTION: (
        "pause",
        "paus",
        "paws",
        "stop",
        "halt",
        "pausa",
        "pausar",
        "pare",
    ),
    SPOTIFY_RESUME_ACTION: (
        "resume",
        "resum",
        "continue",
        "continua",
        "continuar",
        "reanuda",
        "reanudar",
        "retoma",
        "retomar",
    ),
    SPOTIFY_PLAY_ACTION: (
        "play",
        "start",
        "begin",
        "reproducir",
        "iniciar",
        "toca",
    ),
    SPOTIFY_NEXT_ACTION: (
        "next",
        "skip",
        "siguiente",
        "proxima",
    ),
    SPOTIFY_PREVIOUS_ACTION: (
        "previous",
        "back",
        "anterior",
        "atras",
    ),
}
_MUSIC_ALIASES = (
    "music",
    "musica",
    "musik",
    "mizik",
    "musique",
    "spotify",
    "spatify",
    "song",
    "track",
    "audio",
)
_FILLER_TOKENS = frozenset(
    {
        "again",
        "akiha",
        "can",
        "could",
        "it",
        "now",
        "please",
        "that",
        "the",
        "this",
        "would",
        "you",
    }
)
_CONTROL_TOKENS = frozenset(
    alias for aliases in _ACTION_ALIASES.values() for alias in aliases
)
_ACTION_LABELS = {
    SPOTIFY_PLAY_ACTION: "play",
    SPOTIFY_PAUSE_ACTION: "pause",
    SPOTIFY_RESUME_ACTION: "resume",
    SPOTIFY_NEXT_ACTION: "skip to the next track",
    SPOTIFY_PREVIOUS_ACTION: "return to the previous track",
}


@dataclass(frozen=True, slots=True)
class ContextualSpotifyIntent:
    """One locally inferred action or fixed clarification, never both."""

    action_id: str = ""
    clarification: str = ""

    def __post_init__(self) -> None:
        if bool(self.action_id) == bool(self.clarification):
            raise ValueError("contextual Spotify intent requires one outcome.")


class ContextualSpotifyIntentResolver:
    """Resolve only strong Spotify candidates supported by recent state."""

    def resolve(
        self,
        text: str,
        *,
        playback_state: str,
    ) -> ContextualSpotifyIntent | None:
        if playback_state not in {"unknown", "playing", "paused"}:
            raise ValueError("contextual Spotify playback state is invalid.")
        tokens = _fold_tokens(text)
        if not tokens:
            return None
        has_music_context = _best_alias_score(tokens, _MUSIC_ALIASES) >= 0.72
        ranked = sorted(
            (
                (_best_alias_score(tokens, aliases), action_id)
                for action_id, aliases in _ACTION_ALIASES.items()
            ),
            reverse=True,
        )
        best_score, action_id = ranked[0]
        second_score, second_action_id = ranked[1]
        state_supports_action = (
            playback_state == "paused"
            and action_id in {SPOTIFY_PLAY_ACTION, SPOTIFY_RESUME_ACTION}
        ) or (playback_state == "playing" and action_id == SPOTIFY_PAUSE_ACTION)
        if not has_music_context and any(
            token not in _CONTROL_TOKENS and token not in _FILLER_TOKENS
            for token in tokens
        ):
            state_supports_action = False
        required_score = (
            _MATCH_THRESHOLD
            if has_music_context
            else 0.9 if state_supports_action else 1.01
        )
        if best_score < required_score:
            if has_music_context and best_score >= _CLARIFY_THRESHOLD:
                return _clarification(action_id, second_action_id)
            return None
        if second_score >= best_score - _AMBIGUITY_MARGIN:
            resolved = _resolve_play_resume_ambiguity(
                action_id,
                second_action_id,
                playback_state,
            )
            if resolved is None:
                return _clarification(action_id, second_action_id)
            action_id = resolved
        elif playback_state == "paused" and action_id == SPOTIFY_PLAY_ACTION:
            action_id = SPOTIFY_RESUME_ACTION
        return ContextualSpotifyIntent(action_id=action_id)


def _resolve_play_resume_ambiguity(
    first_action_id: str,
    second_action_id: str,
    playback_state: str,
) -> str | None:
    if {first_action_id, second_action_id} != {
        SPOTIFY_PLAY_ACTION,
        SPOTIFY_RESUME_ACTION,
    }:
        return None
    if playback_state == "paused":
        return SPOTIFY_RESUME_ACTION
    if playback_state == "playing":
        return SPOTIFY_PLAY_ACTION
    return None


def _fold_tokens(text: str) -> tuple[str, ...]:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    ascii_like = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return tuple(re.findall(r"[a-z0-9]+", ascii_like))


def _best_alias_score(tokens: tuple[str, ...], aliases: tuple[str, ...]) -> float:
    return max(
        (
            SequenceMatcher(None, token, alias).ratio()
            for token in tokens
            for alias in aliases
        ),
        default=0.0,
    )


def _clarification(
    first_action_id: str,
    second_action_id: str,
) -> ContextualSpotifyIntent:
    first = _ACTION_LABELS[first_action_id]
    second = _ACTION_LABELS[second_action_id]
    return ContextualSpotifyIntent(
        clarification=(
            f"I may have misheard that. Should I {first} or {second} Spotify?"
        )
    )
