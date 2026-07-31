"""Constrained LLM proposals for permission-gated assistant actions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from project_akiha.core.actions import ActionRequest, FileSearchMatch
from project_akiha.core.actions.registry import (
    ALLOWLISTED_APPLICATION_IDS,
    OPEN_FILE_ACTION,
)
from project_akiha.providers.ai import AIProvider, ChatMessage

_MAX_QUERY_LENGTH = 160
_MEDIA_EXTENSIONS = frozenset(
    {
        ".avi",
        ".flac",
        ".m4a",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".ogg",
        ".wav",
        ".webm",
    }
)
_AUDIO_EXTENSIONS = frozenset({".flac", ".m4a", ".mp3", ".ogg", ".wav"})
_VIDEO_EXTENSIONS = _MEDIA_EXTENSIONS - _AUDIO_EXTENSIONS
_RESULT_FOLLOW_UP_PATTERN = re.compile(
    r"^(?:(?:please|akiha[,.]?)\s+)*(?:play|open)\s+result\s+(?P<index>\d+)[.!?]?$",
    re.IGNORECASE,
)
_TOOL_LIKELIHOOD_PATTERN = re.compile(
    r"\b(?:launch|listen|open|play|start|watch)\b|(?:再生|開いて|起動)",
    re.IGNORECASE,
)
_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)
_IGNORED_QUERY_TOKENS = frozenset({"a", "an", "by", "play", "the"})


class AssistantToolKind(StrEnum):
    """Action categories an LLM may propose without execution authority."""

    NONE = "none"
    LAUNCH_APPLICATION = "launch_application"
    PLAY_MEDIA = "play_media"


class MediaKind(StrEnum):
    """Passive media categories supported by the local resolver."""

    ANY = "any"
    AUDIO = "audio"
    VIDEO = "video"


@dataclass(frozen=True, slots=True)
class AssistantToolProposal:
    """Validated, non-executable proposal returned by an AI provider."""

    kind: AssistantToolKind
    application_id: str = ""
    title: str = ""
    artist: str = ""
    media_kind: MediaKind = MediaKind.ANY

    def __post_init__(self) -> None:
        if self.kind is AssistantToolKind.LAUNCH_APPLICATION:
            if self.application_id not in ALLOWLISTED_APPLICATION_IDS:
                raise ValueError("tool proposal application is not allowlisted.")
            if self.title or self.artist:
                raise ValueError("application proposal cannot include media fields.")
        elif self.kind is AssistantToolKind.PLAY_MEDIA:
            if not self.title.strip():
                raise ValueError("media proposal requires a title.")
            _validate_query_text(self.title, "media title")
            if self.artist:
                _validate_query_text(self.artist, "media artist")
            if self.application_id:
                raise ValueError("media proposal cannot include an application.")
        elif any((self.application_id, self.title, self.artist)):
            raise ValueError("none proposal cannot include action fields.")


class AssistantToolProposalError(RuntimeError):
    """Raised when an AI provider returns an invalid tool proposal."""


class LLMAssistantToolGateway:
    """Ask the selected provider for one proposal, never direct execution."""

    def __init__(self, provider: AIProvider, *, enabled: bool = False) -> None:
        self._provider = provider
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """Return whether proposal requests are allowed."""
        return self._enabled

    def apply_provider(self, provider: AIProvider) -> None:
        """Use the currently selected chat provider for future proposals."""
        self._provider = provider

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable LLM-assisted action proposals."""
        self._enabled = enabled

    async def propose(self, user_text: str) -> AssistantToolProposal:
        """Return one validated proposal for explicit everyday action requests."""
        if not self._enabled:
            return AssistantToolProposal(AssistantToolKind.NONE)
        normalized = user_text.strip()
        if not normalized:
            return AssistantToolProposal(AssistantToolKind.NONE)

        response = await self._provider.generate_response(
            (
                ChatMessage(role="system", content=_proposal_system_prompt()),
                ChatMessage(role="user", content=normalized),
            )
        )
        return parse_assistant_tool_proposal(response)


class AssistantToolResultStore:
    """Retain local search results without exposing their paths to an LLM."""

    def __init__(self) -> None:
        self._matches: tuple[FileSearchMatch, ...] = ()

    @property
    def matches(self) -> tuple[FileSearchMatch, ...]:
        """Return the latest validated passive-media matches."""
        return self._matches

    def replace(self, matches: tuple[FileSearchMatch, ...]) -> None:
        """Replace the latest results after filtering to passive media."""
        if any(
            Path(match.path).suffix.casefold() not in _MEDIA_EXTENSIONS
            for match in matches
        ):
            raise ValueError("tool result store accepts only passive media files.")
        self._matches = tuple(matches)

    def clear(self) -> None:
        """Discard all opaque follow-up results."""
        self._matches = ()

    def parse_follow_up(self, text: str) -> ActionRequest | None:
        """Resolve an explicit result number locally into a typed open request."""
        match = _RESULT_FOLLOW_UP_PATTERN.fullmatch(text.strip())
        if match is None:
            return None
        index = int(match.group("index"))
        if index <= 0 or index > len(self._matches):
            return None
        selected = self._matches[index - 1]
        return ActionRequest(
            correlation_id=f"tool-result-{uuid4().hex}",
            action_id=OPEN_FILE_ACTION,
            source="tool_followup",
            parameters={"path": selected.path},
        )


def parse_assistant_tool_proposal(response: str) -> AssistantToolProposal:
    """Parse one exact JSON object and reject invented fields or targets."""
    payload = _parse_json_object(response)
    action = payload.get("action")
    if action == AssistantToolKind.NONE.value:
        _require_exact_keys(payload, {"action"})
        return AssistantToolProposal(AssistantToolKind.NONE)
    if action == AssistantToolKind.LAUNCH_APPLICATION.value:
        _require_exact_keys(payload, {"action", "application_id"})
        application_id = payload.get("application_id")
        if not isinstance(application_id, str):
            raise AssistantToolProposalError("application_id must be a string.")
        try:
            return AssistantToolProposal(
                AssistantToolKind.LAUNCH_APPLICATION,
                application_id=application_id.strip().casefold(),
            )
        except ValueError as error:
            raise AssistantToolProposalError(str(error)) from error
    if action == AssistantToolKind.PLAY_MEDIA.value:
        _require_exact_keys(
            payload,
            {"action", "title", "artist", "media_kind"},
        )
        title = payload.get("title")
        artist = payload.get("artist")
        media_kind = payload.get("media_kind")
        if not isinstance(title, str) or not isinstance(artist, str):
            raise AssistantToolProposalError("media fields must be strings.")
        if not isinstance(media_kind, str):
            raise AssistantToolProposalError("media_kind must be a string.")
        try:
            return AssistantToolProposal(
                AssistantToolKind.PLAY_MEDIA,
                title=title.strip(),
                artist=artist.strip(),
                media_kind=MediaKind(media_kind.strip().casefold()),
            )
        except ValueError as error:
            raise AssistantToolProposalError(str(error)) from error
    raise AssistantToolProposalError("tool proposal action is unsupported.")


def filter_media_matches(
    matches: tuple[FileSearchMatch, ...],
    proposal: AssistantToolProposal,
) -> tuple[FileSearchMatch, ...]:
    """Return deterministic media matches for one validated proposal."""
    if proposal.kind is not AssistantToolKind.PLAY_MEDIA:
        raise ValueError("media filtering requires a play_media proposal.")
    required_tokens = _query_tokens(f"{proposal.title} {proposal.artist}")
    if not required_tokens:
        return ()

    allowed_extensions = {
        MediaKind.ANY: _MEDIA_EXTENSIONS,
        MediaKind.AUDIO: _AUDIO_EXTENSIONS,
        MediaKind.VIDEO: _VIDEO_EXTENSIONS,
    }[proposal.media_kind]
    candidates: list[FileSearchMatch] = []
    seen_paths: set[str] = set()
    for match in matches:
        path = Path(match.path)
        if path.suffix.casefold() not in allowed_extensions:
            continue
        name_tokens = set(_query_tokens(path.stem))
        if not required_tokens.issubset(name_tokens):
            continue
        normalized_path = str(path).casefold()
        if normalized_path in seen_paths:
            continue
        seen_paths.add(normalized_path)
        candidates.append(match)

    return tuple(
        sorted(
            candidates,
            key=lambda match: (
                len(Path(match.path).stem),
                Path(match.path).name.casefold(),
                match.path.casefold(),
            ),
        )
    )


def should_request_tool_proposal(user_text: str) -> bool:
    """Return whether explicit action language justifies an extra LLM request."""
    return _TOOL_LIKELIHOOD_PATTERN.search(user_text.strip()) is not None


def _proposal_system_prompt() -> str:
    return """You classify explicit user requests for a desktop companion.
Return exactly one JSON object and no prose.

Supported outputs:
{"action":"none"}
{"action":"launch_application","application_id":"chrome|discord|spotify|vscode"}
{"action":"play_media","title":"title only","artist":"artist or empty",
 "media_kind":"audio|video|any"}

Choose an action only when the user explicitly asks to launch an allowed
application or play/open local audio or video. Separate artist from title.
Never output paths, commands, URLs, arguments, file contents, or other fields.
For questions, planning, discussion, uncertain intent, or unsupported actions,
return {"action":"none"}."""


def _parse_json_object(response: str) -> dict[str, object]:
    normalized = response.strip()
    if normalized.startswith("```") and normalized.endswith("```"):
        lines = normalized.splitlines()
        if len(lines) >= 3:
            normalized = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError as error:
        raise AssistantToolProposalError(
            "AI tool proposal was not valid JSON."
        ) from error
    if not isinstance(payload, dict):
        raise AssistantToolProposalError("AI tool proposal must be a JSON object.")
    return payload


def _require_exact_keys(payload: dict[str, object], expected: set[str]) -> None:
    if set(payload) != expected:
        raise AssistantToolProposalError(
            "AI tool proposal contained missing or unsupported fields."
        )


def _validate_query_text(value: str, label: str) -> None:
    normalized = value.strip()
    if not normalized or len(normalized) > _MAX_QUERY_LENGTH:
        raise ValueError(
            f"{label} must be between 1 and {_MAX_QUERY_LENGTH} characters."
        )
    if any(character in normalized for character in ("\\", "/", ":", "\0", "\r", "\n")):
        raise ValueError(f"{label} cannot contain path or control characters.")


def _query_tokens(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in (match.casefold() for match in _TOKEN_PATTERN.findall(value))
        if token not in _IGNORED_QUERY_TOKENS
    )
