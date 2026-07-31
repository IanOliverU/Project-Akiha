"""Convert explicit user action commands into typed assistant requests."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

from project_akiha.core.actions import (
    ActionCancellationToken,
    ActionRequest,
    ActionResult,
)
from project_akiha.core.actions.registry import (
    CLOSE_APPLICATION_ACTION,
    FILE_SEARCH_ACTION,
    LAUNCH_APPLICATION_ACTION,
    OPEN_DIRECTORY_ACTION,
    OPEN_FILE_ACTION,
    SPOTIFY_NEXT_ACTION,
    SPOTIFY_OPEN_ARTIST_ACTION,
    SPOTIFY_PAUSE_ACTION,
    SPOTIFY_PLAY_ACTION,
    SPOTIFY_PLAY_ARTIST_ACTION,
    SPOTIFY_PREVIOUS_ACTION,
    SPOTIFY_RESUME_ACTION,
    SPOTIFY_SEARCH_ARTISTS_ACTION,
)
from project_akiha.services.assistant_actions import AssistantActionService
from project_akiha.services.spoken_text import strip_speech_echo_wrappers

_OPEN_DIRECTORY_PATTERN = re.compile(
    r"^(?:(?:/open-dir)\s+|(?:open\s+(?:directory|folder))\s*[:=]\s*)" r"(?P<path>.+)$",
    re.IGNORECASE,
)
_SPOKEN_OPEN_DIRECTORY_PATTERN = re.compile(
    r"^(?:(?:(?:hello|hi)\s+)?akiha[,.]?\s+)?"
    r"(?:(?:please|can you|could you|would you)\s+)?"
    r"open\s+(?:the\s+)?(?:directory|folder)\s+"
    r"(?P<path>(?:[a-z]:[\\/]|\\\\).+)[.!?]?$",
    re.IGNORECASE,
)
_SPOKEN_OPEN_DIRECTORY_ALIAS_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?|"
    r"i\s+(?:want|need)\s+you\s+to)\s+)?"
    r"open\s+(?:the\s+)?(?P<alias>[a-z0-9_-]+)"
    r"(?:\s+(?:directory|folder))?(?:\s+directly)?[.!?]?$",
    re.IGNORECASE,
)
_SEARCH_FILES_PATTERN = re.compile(
    r"^(?:(?:/search-files)\s+|(?:search\s+files)\s*[:=]\s*)"
    r"(?P<query>[^|]+?)\s*\|\s*(?P<root>.+)$",
    re.IGNORECASE,
)
_OPEN_FILE_PATTERN = re.compile(
    r"^(?:(?:/open-file)\s+|(?:open\s+file)\s*[:=]\s*)" r"(?P<path>.+)$",
    re.IGNORECASE,
)
_LAUNCH_APPLICATION_PATTERN = re.compile(
    r"^(?:(?:/launch-app|/open-app)\s+|(?:launch|open)\s+app\s*[:=]\s*)"
    r"(?P<application_id>[a-z0-9_-]+)$",
    re.IGNORECASE,
)
_CLOSE_APPLICATION_PATTERN = re.compile(
    r"^(?:(?:/close-app)\s+|(?:close|quit|exit)\s+app\s*[:=]\s*)"
    r"(?P<application_id>[a-z0-9_-]+)$",
    re.IGNORECASE,
)
_SPOKEN_LAUNCH_APPLICATION_PATTERN = re.compile(
    r"^(?:(?:(?:hello|hi)\s+)?akiha[,.]?\s+)?"
    r"(?:(?:please|can you|could you|would you)\s+)?"
    r"(?:open|launch|start)\s+(?:the\s+)?(?:this\s+)?"
    r"(?P<application>google\s+chrome|visual\s+studio\s+code|"
    r"visuals?\s+to\s+(?:the\s+)?code|vs\s+code|vscode|"
    r"chrome|discord|spotify|vlc(?:\s+media\s+player)?|code)"
    r"(?:\s+(?:application|app))?[.!?]?$",
    re.IGNORECASE,
)
_SPOKEN_CLOSE_APPLICATION_PATTERN = re.compile(
    r"^(?:(?:(?:hello|hi)\s+)?akiha[,.]?\s+)?"
    r"(?:(?:please|can you|could you|would you)\s+)?"
    r"(?:close|quit|exit)\s+(?:the\s+)?"
    r"(?P<application>google\s+chrome|visual\s+studio\s+code|"
    r"vs\s+code|vscode|chrome|discord|spotify|"
    r"vlc(?:\s+media\s+player)?|code)"
    r"(?:\s+(?:application|app))?[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_CONTROL_SEPARATOR = r"[\s,;:.-]+"
_SPOTIFY_TARGET = r"(?:spotify|spatify)(?:\s+playback)?|music|playback|song|track"
_SPOTIFY_ARTIST_SEARCH_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-search-artists\s+(?P<slash>.+?)|"
    r"(?:search|find|look\s+up)\s+(?:for\s+)?(?:spotify\s+)?artists?"
    r"(?:\s+(?:for|named))?\s*[:=]?\s*(?P<labeled>.+?)"
    r"(?:\s+on\s+spotify)?|"
    r"(?:search|find|look\s+up)\s+spotify\s+for\s+(?:the\s+)?artist\s+"
    r"(?P<spotify_for>.+?)|"
    r"(?:search|find|look\s+up)\s+(?:for\s+)?(?P<on_spotify>.+?)"
    r"\s+on\s+spotify)\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_ARTIST_OPEN_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-open-artist\s+|"
    r"(?:open|view|show\s+me|take\s+me\s+to)\s+(?:the\s+)?"
    r"(?:spotify\s+)?artist\s+)(?P<artist>.+?)(?:\s+on\s+spotify)?"
    r"\s*[.!?]?$|"
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:open|view|show\s+me|take\s+me\s+to|go\s+to)\s+"
    r"(?P<page_artist>.+?)(?:'s|\u2019s)\s+spotify(?:\s+artist)?\s+page"
    r"\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_ARTIST_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-artist\s+|"
    r"(?:play|listen\s+to)\s+(?:(?:some\s+)?(?:music|songs|tracks|catalog)\s+"
    r"(?:by|from)\s+|(?:the\s+)?artist\s*[:=]?\s+))"
    r"(?P<artist>.+?)(?:\s+on\s+spotify)?\s*[.!?]?$|"
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"play\s+(?P<possessive_artist>.+?)(?:'s|\u2019s)\s+"
    r"(?:catalog|music|songs)(?:\s+on\s+spotify)?\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_PLAYBACK_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-(?P<slash>play|pause|resume|next|previous)|"
    rf"(?P<play>play){_SPOTIFY_CONTROL_SEPARATOR}(?:the\s+)?"
    rf"(?:{_SPOTIFY_TARGET})|"
    rf"(?P<pause>pause|paws|pos|puzz|stop){_SPOTIFY_CONTROL_SEPARATOR}"
    rf"(?:the\s+)?(?:{_SPOTIFY_TARGET})|"
    rf"(?P<resume>resume|continue){_SPOTIFY_CONTROL_SEPARATOR}(?:the\s+)?"
    rf"(?:{_SPOTIFY_TARGET})|"
    rf"(?P<next>next|skip){_SPOTIFY_CONTROL_SEPARATOR}(?:the\s+)?(?:song|track)|"
    rf"(?P<previous>(?:previous|last){_SPOTIFY_CONTROL_SEPARATOR}"
    r"(?:song|track)|go\s+back\s+to\s+(?:the\s+)?previous\s+(?:song|track)))"
    r"\s*[.!?]?$",
    re.IGNORECASE,
)

_SPOTIFY_ACTIONS = {
    "play": SPOTIFY_PLAY_ACTION,
    "pause": SPOTIFY_PAUSE_ACTION,
    "resume": SPOTIFY_RESUME_ACTION,
    "next": SPOTIFY_NEXT_ACTION,
    "previous": SPOTIFY_PREVIOUS_ACTION,
}

_APPLICATION_ALIASES = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "discord": "discord",
    "spotify": "spotify",
    "vlc": "vlc",
    "vlc media player": "vlc",
    "code": "vscode",
    "vs code": "vscode",
    "vscode": "vscode",
    "visual to code": "vscode",
    "visual to the code": "vscode",
    "visuals to code": "vscode",
    "visuals to the code": "vscode",
    "visual studio code": "vscode",
}

_VOICE_FILLER_PATTERN = re.compile(
    r"^(?:okay|ok|alright|all\s+right|hey|ha)"
    r"(?:\s*,?\s*(?:huh|uh|um))?\s*[,!.?]?\s*",
    re.IGNORECASE,
)
_VOICE_CONTEXT_FILLER_PATTERN = re.compile(
    r"^(?:(?:so\s+)?for\s+now|so)\s*[,!.?]?\s*",
    re.IGNORECASE,
)
_VOICE_NAME_PATTERN = re.compile(
    r"^(?:(?:hello|hi)\s+)?(?:akiha|akia|akaya|aka['’]?ya)\s*[,!.:?]?\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AssistantActionDispatch:
    """Pair one user-originated typed request with its sanitized result."""

    request: ActionRequest
    result: ActionResult


class AssistantActionRequestParser:
    """Parse only explicit, unambiguous action command forms."""

    def __init__(self, directory_aliases: Mapping[str, str] | None = None) -> None:
        self._directory_aliases: dict[str, str] = {}
        self.set_directory_aliases(directory_aliases or {})

    def set_directory_aliases(self, aliases: Mapping[str, str]) -> None:
        """Replace aliases with paths sourced from active approved directories."""
        self._directory_aliases = {
            alias.strip().casefold(): path.strip()
            for alias, path in aliases.items()
            if alias.strip() and path.strip()
        }

    def parse(
        self, text: str, *, correlation_id: str | None = None
    ) -> ActionRequest | None:
        """Return a typed request for a supported command, otherwise ``None``."""
        normalized = _normalize_voice_wrappers(text)
        if not normalized:
            return None
        request_id = correlation_id or f"chat-action-{uuid4().hex}"

        artist_search_match = _SPOTIFY_ARTIST_SEARCH_PATTERN.fullmatch(normalized)
        if artist_search_match is not None:
            artist = next(
                value
                for group in ("slash", "labeled", "spotify_for", "on_spotify")
                if (value := artist_search_match.group(group)) is not None
            ).strip()
            if artist:
                return _request(
                    correlation_id=request_id,
                    action_id=SPOTIFY_SEARCH_ARTISTS_ACTION,
                    parameters={
                        "service": "spotify",
                        "artist_query": artist,
                    },
                )

        artist_open_match = _SPOTIFY_ARTIST_OPEN_PATTERN.fullmatch(normalized)
        if artist_open_match is not None:
            artist = (
                artist_open_match.group("artist")
                or artist_open_match.group("page_artist")
            ).strip()
            if artist:
                return _request(
                    correlation_id=request_id,
                    action_id=SPOTIFY_OPEN_ARTIST_ACTION,
                    parameters={
                        "service": "spotify",
                        "artist_query": artist,
                    },
                )

        artist_match = _SPOTIFY_ARTIST_PATTERN.fullmatch(normalized)
        if artist_match is not None:
            artist = (
                artist_match.group("artist") or artist_match.group("possessive_artist")
            ).strip()
            if artist:
                return _request(
                    correlation_id=request_id,
                    action_id=SPOTIFY_PLAY_ARTIST_ACTION,
                    parameters={
                        "service": "spotify",
                        "artist_query": artist,
                    },
                )

        spotify_match = _SPOTIFY_PLAYBACK_PATTERN.fullmatch(normalized)
        if spotify_match is not None:
            command = next(
                name
                for name in ("slash", "play", "pause", "resume", "next", "previous")
                if spotify_match.group(name) is not None
            )
            if command == "slash":
                command = spotify_match.group("slash").casefold()
            elif command in {"next", "previous"}:
                command = command
            return _request(
                correlation_id=request_id,
                action_id=_SPOTIFY_ACTIONS[command],
                parameters={"service": "spotify"},
            )

        open_match = _OPEN_DIRECTORY_PATTERN.fullmatch(normalized)
        if open_match is not None:
            return _request(
                correlation_id=request_id,
                action_id=OPEN_DIRECTORY_ACTION,
                parameters={"path": open_match.group("path").strip()},
            )

        spoken_open_match = _SPOKEN_OPEN_DIRECTORY_PATTERN.fullmatch(normalized)
        if spoken_open_match is not None:
            return _request(
                correlation_id=request_id,
                action_id=OPEN_DIRECTORY_ACTION,
                parameters={
                    "path": spoken_open_match.group("path").strip().rstrip(".!?")
                },
            )

        alias_match = _SPOKEN_OPEN_DIRECTORY_ALIAS_PATTERN.fullmatch(normalized)
        if alias_match is not None:
            alias = alias_match.group("alias").casefold()
            path = self._directory_aliases.get(alias)
            if path is not None:
                return _request(
                    correlation_id=request_id,
                    action_id=OPEN_DIRECTORY_ACTION,
                    parameters={"path": path},
                )

        file_match = _OPEN_FILE_PATTERN.fullmatch(normalized)
        if file_match is not None:
            return _request(
                correlation_id=request_id,
                action_id=OPEN_FILE_ACTION,
                parameters={"path": file_match.group("path").strip()},
            )

        application_match = _LAUNCH_APPLICATION_PATTERN.fullmatch(normalized)
        if application_match is not None:
            return _request(
                correlation_id=request_id,
                action_id=LAUNCH_APPLICATION_ACTION,
                parameters={
                    "application_id": application_match.group(
                        "application_id"
                    ).casefold()
                },
            )

        close_match = _CLOSE_APPLICATION_PATTERN.fullmatch(normalized)
        if close_match is not None:
            return _request(
                correlation_id=request_id,
                action_id=CLOSE_APPLICATION_ACTION,
                parameters={
                    "application_id": close_match.group("application_id").casefold()
                },
            )

        spoken_close_match = _SPOKEN_CLOSE_APPLICATION_PATTERN.fullmatch(normalized)
        if spoken_close_match is not None:
            application = spoken_close_match.group("application").casefold()
            return _request(
                correlation_id=request_id,
                action_id=CLOSE_APPLICATION_ACTION,
                parameters={"application_id": _APPLICATION_ALIASES[application]},
            )

        spoken_application_match = _SPOKEN_LAUNCH_APPLICATION_PATTERN.fullmatch(
            normalized
        )
        if spoken_application_match is not None:
            application = spoken_application_match.group("application").casefold()
            return _request(
                correlation_id=request_id,
                action_id=LAUNCH_APPLICATION_ACTION,
                parameters={"application_id": _APPLICATION_ALIASES[application]},
            )

        search_match = _SEARCH_FILES_PATTERN.fullmatch(normalized)
        if search_match is not None:
            return _request(
                correlation_id=request_id,
                action_id=FILE_SEARCH_ACTION,
                parameters={
                    "query": search_match.group("query").strip(),
                    "root": search_match.group("root").strip(),
                },
            )
        return None


class AssistantActionBridge:
    """Dispatch parsed user requests through the existing action service."""

    def __init__(
        self,
        action_service: AssistantActionService,
        parser: AssistantActionRequestParser | None = None,
    ) -> None:
        self._action_service = action_service
        self._parser = parser or AssistantActionRequestParser()

    def parse_user_text(
        self,
        text: str,
        *,
        correlation_id: str | None = None,
    ) -> ActionRequest | None:
        """Parse only user text; provider responses are never accepted here."""
        return self._parser.parse(text, correlation_id=correlation_id)

    def set_directory_aliases(self, aliases: Mapping[str, str]) -> None:
        """Update path aliases from the current approved-directory grants."""
        self._parser.set_directory_aliases(aliases)

    async def dispatch(
        self,
        request: ActionRequest,
        *,
        confirmed: bool = False,
        cancellation_token: ActionCancellationToken | None = None,
    ) -> AssistantActionDispatch:
        """Evaluate one already-parsed request through validation and policy."""
        if not isinstance(request, ActionRequest):
            raise TypeError("assistant action bridge requires a typed request.")
        result = await self._action_service.evaluate_request(
            request,
            confirmed=confirmed,
            cancellation_token=cancellation_token,
        )
        return AssistantActionDispatch(request=request, result=result)


def _request(
    *,
    correlation_id: str,
    action_id: str,
    parameters: dict[str, object],
) -> ActionRequest:
    return ActionRequest(
        correlation_id=correlation_id,
        action_id=action_id,
        source="chat",
        parameters=parameters,
    )


def _normalize_voice_wrappers(text: str) -> str:
    """Remove common speech-recognition wrappers before strict parsing."""
    normalized = strip_speech_echo_wrappers(text)
    while normalized:
        unwrapped = normalized
        for pattern in (
            _VOICE_FILLER_PATTERN,
            _VOICE_CONTEXT_FILLER_PATTERN,
            _VOICE_NAME_PATTERN,
        ):
            unwrapped = pattern.sub("", unwrapped, count=1).strip()
        if unwrapped == normalized:
            break
        normalized = unwrapped
    return normalized
