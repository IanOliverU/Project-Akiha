"""Constrained LLM proposals for permission-gated assistant actions."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from project_akiha.core.actions import (
    ActionRequest,
    DirectorySearchMatch,
    FileSearchMatch,
)
from project_akiha.core.actions.registry import (
    ALLOWLISTED_APPLICATION_IDS,
    OPEN_DIRECTORY_ACTION,
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
    r"^(?:(?:please|akiha[,.]?)\s+)*(?P<verb>play|open)\s+result\s+"
    r"(?P<index>\d+)[.!?]?$",
    re.IGNORECASE,
)
_DIRECTORY_IN_PARENT_PATTERN = re.compile(
    r"^(?:(?:please|akiha[,.]?)\s+)*(?:open|find)\s+(?:the\s+)?"
    r"(?P<name>.+?)(?:\s+(?:folder|directory))?\s+"
    r"(?:inside|in|under)\s+(?:the\s+)?"
    r"(?P<parent>.+?)(?:\s+(?:folder|directory))?[.!?]?$",
    re.IGNORECASE,
)
_DIRECTORY_CONTEXT_PATTERN = re.compile(
    r"^(?:(?:please|akiha[,.]?)\s+)*(?:now\s+)?open\s+(?:the\s+)?"
    r"(?P<name>.+?)(?:\s+(?:folder|directory))?[.!?]?$",
    re.IGNORECASE,
)
_NAVIGATION_VOICE_WRAPPER_PATTERN = re.compile(
    r"^(?:i\s+heard\s+you\s+say\s*:\s*)+",
    re.IGNORECASE,
)
_NAVIGATION_FILLER_PATTERN = re.compile(
    r"^(?:okay|ok|alright|all\s+right|hey)" r"(?:\s*,?\s*(?:huh|uh|um))?\s*[,!.?]?\s*",
    re.IGNORECASE,
)
_NAVIGATION_NAME_PATTERN = re.compile(
    r"^(?:(?:hello|hi)\s+)?(?:akiha|akia|akaya|aka['’]?ya)" r"\s*[,!.:?]?\s*",
    re.IGNORECASE,
)
_TOOL_LIKELIHOOD_PATTERN = re.compile(
    r"\b(?:close|exit|launch|listen|open|play|quit|start|watch)\b|"
    r"(?:再生|開いて|起動)",
    re.IGNORECASE,
)
_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)
_IGNORED_QUERY_TOKENS = frozenset({"a", "an", "by", "play", "the"})


class AssistantToolKind(StrEnum):
    """Action categories an LLM may propose without execution authority."""

    NONE = "none"
    LAUNCH_APPLICATION = "launch_application"
    CLOSE_APPLICATION = "close_application"
    PLAY_MEDIA = "play_media"
    OPEN_DIRECTORY = "open_directory"


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
    directory_name: str = ""
    parent_name: str = ""

    def __post_init__(self) -> None:
        if self.kind in {
            AssistantToolKind.LAUNCH_APPLICATION,
            AssistantToolKind.CLOSE_APPLICATION,
        }:
            if self.application_id not in ALLOWLISTED_APPLICATION_IDS:
                raise ValueError("tool proposal application is not allowlisted.")
            if any(
                (
                    self.title,
                    self.artist,
                    self.directory_name,
                    self.parent_name,
                )
            ):
                raise ValueError("application proposal cannot include other fields.")
        elif self.kind is AssistantToolKind.PLAY_MEDIA:
            if not self.title.strip():
                raise ValueError("media proposal requires a title.")
            _validate_query_text(self.title, "media title")
            if self.artist:
                _validate_query_text(self.artist, "media artist")
            if any(
                (
                    self.application_id,
                    self.directory_name,
                    self.parent_name,
                )
            ):
                raise ValueError("media proposal cannot include other fields.")
        elif self.kind is AssistantToolKind.OPEN_DIRECTORY:
            _validate_query_text(self.directory_name, "directory name")
            if self.parent_name:
                _validate_query_text(self.parent_name, "parent directory name")
            if any((self.application_id, self.title, self.artist)):
                raise ValueError("directory proposal cannot include other fields.")
        elif any(
            (
                self.application_id,
                self.title,
                self.artist,
                self.directory_name,
                self.parent_name,
            )
        ):
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
        self._directory_matches: tuple[DirectorySearchMatch, ...] = ()

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
        self._directory_matches = ()

    @property
    def directory_matches(self) -> tuple[DirectorySearchMatch, ...]:
        """Return the latest validated directory matches."""
        return self._directory_matches

    def replace_directories(
        self,
        matches: tuple[DirectorySearchMatch, ...],
    ) -> None:
        """Replace the latest results with validated directory matches."""
        self._directory_matches = tuple(matches)
        self._matches = ()

    def clear(self) -> None:
        """Discard all opaque follow-up results."""
        self._matches = ()
        self._directory_matches = ()

    def parse_follow_up(self, text: str) -> ActionRequest | None:
        """Resolve an explicit result number locally into a typed open request."""
        match = _RESULT_FOLLOW_UP_PATTERN.fullmatch(text.strip())
        if match is None:
            return None
        index = int(match.group("index"))
        if self._directory_matches:
            if match.group("verb").casefold() != "open":
                return None
            if index <= 0 or index > len(self._directory_matches):
                return None
            selected_directory = self._directory_matches[index - 1]
            return ActionRequest(
                correlation_id=f"tool-directory-result-{uuid4().hex}",
                action_id=OPEN_DIRECTORY_ACTION,
                source="tool_followup",
                parameters={"path": selected_directory.path},
            )
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
    if action == AssistantToolKind.CLOSE_APPLICATION.value:
        _require_exact_keys(payload, {"action", "application_id"})
        application_id = payload.get("application_id")
        if not isinstance(application_id, str):
            raise AssistantToolProposalError("application_id must be a string.")
        try:
            return AssistantToolProposal(
                AssistantToolKind.CLOSE_APPLICATION,
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
    if action == AssistantToolKind.OPEN_DIRECTORY.value:
        _require_exact_keys(payload, {"action", "name", "parent"})
        name = payload.get("name")
        parent = payload.get("parent")
        if not isinstance(name, str) or not isinstance(parent, str):
            raise AssistantToolProposalError("directory fields must be strings.")
        try:
            return AssistantToolProposal(
                AssistantToolKind.OPEN_DIRECTORY,
                directory_name=name.strip(),
                parent_name=parent.strip(),
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
    title_tokens = _query_tokens(proposal.title)
    artist_tokens = _query_tokens(proposal.artist)
    if not title_tokens:
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
        name_tokens = _query_tokens(path.stem)
        if not _tokens_are_represented(title_tokens, name_tokens):
            continue
        if artist_tokens and not _tokens_are_represented(
            artist_tokens,
            name_tokens,
        ):
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


def build_media_search_queries(
    proposal: AssistantToolProposal,
) -> tuple[str, ...]:
    """Build a bounded sequence of local lookup terms from one media intent."""
    if proposal.kind is not AssistantToolKind.PLAY_MEDIA:
        raise ValueError("media search queries require a play_media proposal.")

    candidates = (
        proposal.title,
        proposal.artist,
        *sorted(_query_tokens(proposal.artist)),
        *sorted(_query_tokens(proposal.title)),
    )
    queries: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        queries.append(normalized)
        if len(queries) >= 5:
            break
    if "." not in seen:
        queries.append(".")
    return tuple(queries)


def parse_directory_navigation_proposal(
    user_text: str,
    *,
    has_context: bool,
) -> AssistantToolProposal | None:
    """Parse explicit path-free descendant-directory requests locally."""
    normalized = _normalize_navigation_text(user_text)
    parent_match = _DIRECTORY_IN_PARENT_PATTERN.fullmatch(normalized)
    if parent_match is not None:
        try:
            return AssistantToolProposal(
                AssistantToolKind.OPEN_DIRECTORY,
                directory_name=_strip_directory_suffix(parent_match.group("name")),
                parent_name=_strip_directory_suffix(parent_match.group("parent")),
            )
        except ValueError:
            return None
    if not has_context:
        return None
    context_match = _DIRECTORY_CONTEXT_PATTERN.fullmatch(normalized)
    if context_match is None:
        return None
    try:
        return AssistantToolProposal(
            AssistantToolKind.OPEN_DIRECTORY,
            directory_name=_strip_directory_suffix(context_match.group("name")),
        )
    except ValueError:
        return None


def filter_directory_matches(
    matches: tuple[DirectorySearchMatch, ...],
    proposal: AssistantToolProposal,
) -> tuple[DirectorySearchMatch, ...]:
    """Return deterministic fuzzy directory-name matches for one intent."""
    if proposal.kind is not AssistantToolKind.OPEN_DIRECTORY:
        raise ValueError("directory filtering requires an open_directory proposal.")
    required_tokens = _query_tokens(proposal.directory_name)
    if not required_tokens:
        return ()
    seen_paths: set[str] = set()
    filtered: list[DirectorySearchMatch] = []
    for match in matches:
        if not _tokens_are_represented(required_tokens, _query_tokens(match.name)):
            continue
        path_key = match.path.casefold()
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        filtered.append(match)
    return tuple(
        sorted(
            filtered,
            key=lambda match: (
                len(match.name),
                match.name.casefold(),
                match.path.casefold(),
            ),
        )
    )


def directory_name_matches(expected: str, actual: str) -> bool:
    """Return whether a user-facing directory hint matches one local name."""
    expected_tokens = _query_tokens(_strip_directory_suffix(expected))
    actual_tokens = _query_tokens(_strip_directory_suffix(actual))
    return bool(expected_tokens) and _tokens_are_represented(
        expected_tokens,
        actual_tokens,
    )


def should_request_tool_proposal(user_text: str) -> bool:
    """Return whether explicit action language justifies an extra LLM request."""
    return _TOOL_LIKELIHOOD_PATTERN.search(user_text.strip()) is not None


def _proposal_system_prompt() -> str:
    return """You classify explicit user requests for a desktop companion.
Return exactly one JSON object and no prose.

Supported outputs:
{"action":"none"}
{"action":"launch_application","application_id":"chrome|discord|spotify|vlc|vscode"}
{"action":"close_application","application_id":"chrome|discord|spotify|vlc|vscode"}
{"action":"open_directory","name":"child directory name",
 "parent":"parent directory name or empty"}
{"action":"play_media","title":"title only","artist":"artist or empty",
 "media_kind":"audio|video|any"}

Choose an action only when the user explicitly asks to launch an allowed
application, gracefully close an allowed application, open a named local
directory, or play/open local audio or video. Separate artist from title.
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


def _strip_directory_suffix(value: str) -> str:
    return re.sub(
        r"\s+(?:folder|directory)\s*$",
        "",
        value.strip().rstrip(".!?"),
        flags=re.IGNORECASE,
    ).strip()


def _normalize_navigation_text(value: str) -> str:
    normalized = value.strip()
    while normalized:
        unwrapped = _NAVIGATION_VOICE_WRAPPER_PATTERN.sub(
            "",
            normalized,
            count=1,
        ).strip()
        if unwrapped == normalized:
            break
        normalized = unwrapped
    normalized = _NAVIGATION_FILLER_PATTERN.sub("", normalized, count=1).strip()
    return _NAVIGATION_NAME_PATTERN.sub("", normalized, count=1).strip()


def _tokens_are_represented(
    required: frozenset[str],
    candidates: frozenset[str],
) -> bool:
    return all(
        any(_tokens_are_similar(token, candidate) for candidate in candidates)
        for token in required
    )


def _tokens_are_similar(left: str, right: str) -> bool:
    if left == right:
        return True
    if min(len(left), len(right)) >= 4:
        if SequenceMatcher(None, left, right).ratio() >= 0.74:
            return True
    left_soundex = _soundex(left)
    right_soundex = _soundex(right)
    if not left_soundex or not right_soundex:
        return False
    if left_soundex == right_soundex:
        return True
    vowels = frozenset("aeiouy")
    return (
        left[0] in vowels
        and right[0] in vowels
        and left_soundex[1:] == right_soundex[1:]
    )


def _soundex(value: str) -> str:
    ascii_value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value).casefold()
        if "a" <= character <= "z"
    )
    if not ascii_value:
        return ""
    groups = {
        **dict.fromkeys("bfpv", "1"),
        **dict.fromkeys("cgjkqsxz", "2"),
        **dict.fromkeys("dt", "3"),
        "l": "4",
        **dict.fromkeys("mn", "5"),
        "r": "6",
    }
    encoded: list[str] = []
    previous = groups.get(ascii_value[0], "")
    for character in ascii_value[1:]:
        digit = groups.get(character, "")
        if digit and digit != previous:
            encoded.append(digit)
        previous = digit
    return (ascii_value[0].upper() + "".join(encoded) + "000")[:4]
