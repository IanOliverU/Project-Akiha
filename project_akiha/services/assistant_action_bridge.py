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
    SPOTIFY_OPEN_ALBUM_ACTION,
    SPOTIFY_OPEN_ARTIST_ACTION,
    SPOTIFY_PAUSE_ACTION,
    SPOTIFY_PLAY_ACTION,
    SPOTIFY_PLAY_ALBUM_ACTION,
    SPOTIFY_PLAY_ARTIST_ACTION,
    SPOTIFY_PLAY_FAVORITES_ACTION,
    SPOTIFY_PLAY_PLAYLIST_ACTION,
    SPOTIFY_PLAY_TRACK_ACTION,
    SPOTIFY_PREVIOUS_ACTION,
    SPOTIFY_REPEAT_ACTION,
    SPOTIFY_RESUME_ACTION,
    SPOTIFY_SEARCH_ALBUMS_ACTION,
    SPOTIFY_SEARCH_ARTISTS_ACTION,
    SPOTIFY_SEARCH_PLAYLISTS_ACTION,
    SPOTIFY_SEARCH_TRACKS_ACTION,
    SPOTIFY_SEEK_ACTION,
    SPOTIFY_SHUFFLE_ACTION,
    SPOTIFY_VOLUME_ACTION,
)
from project_akiha.services.assistant_actions import AssistantActionService
from project_akiha.services.command_envelope import (
    DeterministicCommandEnvelopeParser,
)
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
_SPOTIFY_TARGET = (
    r"(?:spotify|spatify)(?:\s+(?:music|playback))?|music|playback|song|track"
)
_SPOTIFY_ALBUM_SEARCH_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-search-albums\s+(?P<slash>.+?)|"
    r"(?:search|find|look\s+up)\s+(?:for\s+)?(?:spotify\s+)?albums?"
    r"(?:\s+(?:for|named))?\s*[:=]?\s*(?P<labeled>.+?)"
    r"(?:\s+on\s+spotify)?)\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_PLAYLIST_SEARCH_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-search-playlists\s+(?P<slash>.+?)|"
    r"(?:search|find|look\s+up)\s+(?:for\s+)?(?:spotify\s+)?playlists?"
    r"(?:\s+(?:for|named|called))?\s*[:=]?\s*(?P<labeled>.+?)"
    r"(?:\s+on\s+spotify)?|"
    r"(?:search|find|look\s+up)\s+spotify\s+for\s+(?:the\s+)?playlist\s+"
    r"(?P<spotify_for>.+?))\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_PLAYLIST_PLAY_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-playlist\s+(?P<slash>.+?)|"
    r"(?:play|listen\s+to)\s+(?:(?:my|the)\s+)?(?:spotify\s+)?playlist"
    r"(?:\s+(?:named|called))?\s+(?P<labeled>.+?)(?:\s+on\s+spotify)?|"
    r"play\s+(?P<on_spotify>.+?)\s+playlist\s+on\s+spotify)\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_ALBUM_OPEN_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-open-album\s+(?P<slash>.+?)|"
    r"(?:open|view|show\s+me|take\s+me\s+to)\s+(?:the\s+)?"
    r"(?:spotify\s+)?album\s+(?P<labeled>.+?)(?:\s+on\s+spotify)?|"
    r"(?:open|view|show\s+me|take\s+me\s+to|go\s+to)\s+"
    r"(?P<on_spotify>.+?)\s+album\s+on\s+spotify)\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_ALBUM_PLAY_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-album\s+(?P<slash>.+?)|"
    r"(?:play|listen\s+to)\s+(?:the\s+)?(?:spotify\s+)?album\s+"
    r"(?P<labeled>.+?)(?:\s+on\s+spotify)?|"
    r"play\s+(?P<on_spotify>.+?)\s+album\s+on\s+spotify)\s*[.!?]?$",
    re.IGNORECASE,
)
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
_SPOTIFY_TRACK_SEARCH_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-search-tracks\s+(?P<slash>.+?)|"
    r"(?:search|find|look\s+up)\s+(?:for\s+)?(?:spotify\s+)?"
    r"(?:tracks?|songs?)(?:\s+(?:for|named))?\s*[:=]?\s*"
    r"(?P<labeled>.+?)(?:\s+on\s+spotify)?)\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_TRACK_PLAY_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-track\s+(?P<slash>.+?)|"
    r"(?:play|listen\s+to)\s+(?:the\s+)?(?:spotify\s+)?"
    r"(?:track|song)\s+(?P<labeled>.+?)(?:\s+on\s+spotify)?|"
    r"play\s+(?P<on_spotify>.+?)\s+on\s+spotify)\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_FAVORITES_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-(?P<slash>liked|favorites)|"
    r"(?:play|listen\s+to)\s+(?:(?:some|something|me\s+something)\s+)?"
    r"(?:(?P<liked>(?:my\s+)?(?:spotify\s+)?(?:liked\s+(?:songs|music)|"
    r"saved\s+tracks))|"
    r"(?P<mix>(?:my\s+)?(?:spotify\s+)?(?:favorites?|favourites?)"
    r"(?:\s+(?:songs|music))?|(?:music|(?:me\s+)?something)\s+i\s+like))"
    r"(?:\s+on\s+spotify)?)\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_SHUFFLE_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-shuffle\s+(?P<slash>on|off)|"
    r"(?P<enable>enable|start)\s+(?:spotify\s+)?shuffle|"
    r"(?P<disable>disable|stop)\s+(?:spotify\s+)?shuffle|"
    r"(?:turn|switch)\s+(?:spotify\s+)?shuffle\s+(?P<post_state>on|off)|"
    r"(?:turn|switch)\s+(?P<pre_state>on|off)\s+(?:spotify\s+)?shuffle|"
    r"(?:set\s+)?(?:spotify\s+)?shuffle\s+(?P<state>on|off))"
    r"(?:\s+on\s+spotify)?\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_REPEAT_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-repeat\s+(?P<slash>track|context|off)|"
    r"repeat\s+(?:(?:this|current|the(?:\s+current)?)\s+)?(?:spotify\s+)?"
    r"(?P<target>song|track|album|playlist|context)|"
    r"(?P<disable>disable|stop)\s+(?:spotify\s+)?repeat|"
    r"(?P<turn_off>(?:turn|switch)\s+(?:(?:spotify\s+)?repeat\s+off|"
    r"off\s+(?:spotify\s+)?repeat))|"
    r"(?:set\s+)?(?:spotify\s+)?repeat\s+"
    r"(?P<state>track|context|off))"
    r"(?:\s+on\s+spotify)?\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_VOLUME_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-volume\s+(?P<slash>\d{1,3})|"
    r"(?:(?:set|change|turn|raise|lower|increase|decrease)\s+)?(?:the\s+)?"
    r"(?:spotify|music|playback)\s+volume(?:\s+level)?"
    r"(?:\s+(?:up|down))?(?:\s+(?:to|at))?\s+(?P<spotify_value>.+?)|"
    r"(?:set|change|turn)\s+(?:the\s+)?volume(?:\s+level)?\s+"
    r"(?:to|at)\s+(?P<on_spotify_value>.+?)\s+on\s+spotify|"
    r"(?P<mute>mute)\s+spotify(?:\s+playback)?)\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_SEEK_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-seek\s+(?P<slash>\d{1,5})|"
    r"(?:seek|jump)\s+(?:spotify\s+)(?:playback\s+)?(?:to|at)\s+"
    r"(?P<spotify_value>.+?)|"
    r"spotify\s+(?:seek|jump)(?:\s+playback)?\s+(?:to|at)\s+"
    r"(?P<prefixed_value>.+?)|"
    r"(?:seek|jump|go)\s+(?:playback\s+)?(?:to|at)\s+"
    r"(?P<on_spotify_value>.+?)\s+on\s+spotify|"
    r"(?P<restart>restart)\s+(?:(?:(?:the\s+)?current\s+)?spotify"
    r"(?:\s+(?:song|track|playback))?|"
    r"(?:(?:the\s+)?current\s+)?(?:song|track)\s+on\s+spotify))"
    r"\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_PLAYBACK_PATTERN = re.compile(
    r"^(?:(?:please|(?:can|could|would)\s+you(?:\s+please)?)\s+)?"
    r"(?:/spotify-(?P<slash>play|pause|resume|next|previous)|"
    rf"(?P<play>play){_SPOTIFY_CONTROL_SEPARATOR}(?:(?:the|my)\s+)?"
    rf"(?:{_SPOTIFY_TARGET})|"
    rf"(?P<pause>pause|paws|pos|puzz|stop){_SPOTIFY_CONTROL_SEPARATOR}"
    rf"(?:(?:the|my)\s+)?(?:{_SPOTIFY_TARGET})|"
    rf"(?P<resume>resume|continue){_SPOTIFY_CONTROL_SEPARATOR}"
    rf"(?:(?:the|my)\s+)?"
    rf"(?:{_SPOTIFY_TARGET})|"
    rf"(?P<next>next|skip){_SPOTIFY_CONTROL_SEPARATOR}(?:the\s+)?"
    r"(?:next\s+)?(?:song|track)|"
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
_SMALL_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS_NUMBER_WORDS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
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
_VOICE_TRAILING_NAME_PATTERN = re.compile(
    r"(?:\s*[,;:.!?]?\s*)" r"(?:akiha|akia|akaya|aka['â€™]?ya)" r"(?:\s*[,;:.!?]?\s*)$",
    re.IGNORECASE,
)
_VOICE_SPOTIFY_ALIAS_PATTERN = re.compile(
    r"\b(?:spatify|spotefy|spotifi|swatifi)\b",
    re.IGNORECASE,
)
_SPOTIFY_RESULT_REFERENCE_PATTERN = re.compile(
    r"^result\s+(?:\d+|one|two|three|four|five)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AssistantActionDispatch:
    """Pair one user-originated typed request with its sanitized result."""

    request: ActionRequest
    result: ActionResult


class AssistantActionRequestParser:
    """Parse only explicit, unambiguous action command forms."""

    def __init__(
        self,
        directory_aliases: Mapping[str, str] | None = None,
        command_envelope_parser: DeterministicCommandEnvelopeParser | None = None,
    ) -> None:
        self._directory_aliases: dict[str, str] = {}
        self._command_envelope_parser = (
            command_envelope_parser or DeterministicCommandEnvelopeParser()
        )
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
        envelope = self._command_envelope_parser.parse(normalized)
        if envelope is None:
            return None
        normalized = envelope.command_text

        album_search_match = _SPOTIFY_ALBUM_SEARCH_PATTERN.fullmatch(normalized)
        if album_search_match is not None:
            query = _matched_query(album_search_match, ("slash", "labeled"))
            album, artist = _split_spotify_title_artist_query(query)
            if album and not _is_spotify_result_reference(album):
                parameters = {"service": "spotify", "album_query": album}
                if artist:
                    parameters["artist_query"] = artist
                return _request(
                    correlation_id=request_id,
                    action_id=SPOTIFY_SEARCH_ALBUMS_ACTION,
                    parameters=parameters,
                )

        playlist_search_match = _SPOTIFY_PLAYLIST_SEARCH_PATTERN.fullmatch(normalized)
        if playlist_search_match is not None:
            playlist = _matched_query(
                playlist_search_match,
                ("slash", "labeled", "spotify_for"),
            )
            if playlist and not _is_spotify_result_reference(playlist):
                return _request(
                    correlation_id=request_id,
                    action_id=SPOTIFY_SEARCH_PLAYLISTS_ACTION,
                    parameters={
                        "service": "spotify",
                        "playlist_query": playlist,
                    },
                )

        playlist_play_match = _SPOTIFY_PLAYLIST_PLAY_PATTERN.fullmatch(normalized)
        if playlist_play_match is not None:
            playlist = _matched_query(
                playlist_play_match,
                ("slash", "labeled", "on_spotify"),
            )
            if playlist and not _is_spotify_result_reference(playlist):
                return _request(
                    correlation_id=request_id,
                    action_id=SPOTIFY_PLAY_PLAYLIST_ACTION,
                    parameters={
                        "service": "spotify",
                        "playlist_query": playlist,
                    },
                )

        album_open_match = _SPOTIFY_ALBUM_OPEN_PATTERN.fullmatch(normalized)
        if album_open_match is not None:
            query = _matched_query(
                album_open_match,
                ("slash", "labeled", "on_spotify"),
            )
            album, artist = _split_spotify_title_artist_query(query)
            if album and not _is_spotify_result_reference(album):
                parameters = {"service": "spotify", "album_query": album}
                if artist:
                    parameters["artist_query"] = artist
                return _request(
                    correlation_id=request_id,
                    action_id=SPOTIFY_OPEN_ALBUM_ACTION,
                    parameters=parameters,
                )

        album_play_match = _SPOTIFY_ALBUM_PLAY_PATTERN.fullmatch(normalized)
        if album_play_match is not None:
            query = _matched_query(
                album_play_match,
                ("slash", "labeled", "on_spotify"),
            )
            album, artist = _split_spotify_title_artist_query(query)
            if album and not _is_spotify_result_reference(album):
                parameters = {"service": "spotify", "album_query": album}
                if artist:
                    parameters["artist_query"] = artist
                return _request(
                    correlation_id=request_id,
                    action_id=SPOTIFY_PLAY_ALBUM_ACTION,
                    parameters=parameters,
                )

        track_search_match = _SPOTIFY_TRACK_SEARCH_PATTERN.fullmatch(normalized)
        if track_search_match is not None:
            query = _matched_query(
                track_search_match,
                ("slash", "labeled"),
            )
            track, artist = _split_spotify_title_artist_query(query)
            if track and not _is_spotify_result_reference(track):
                parameters = {
                    "service": "spotify",
                    "track_query": track,
                }
                if artist:
                    parameters["artist_query"] = artist
                return _request(
                    correlation_id=request_id,
                    action_id=SPOTIFY_SEARCH_TRACKS_ACTION,
                    parameters=parameters,
                )

        artist_search_match = _SPOTIFY_ARTIST_SEARCH_PATTERN.fullmatch(normalized)
        if artist_search_match is not None:
            artist = next(
                value
                for group in ("slash", "labeled", "spotify_for", "on_spotify")
                if (value := artist_search_match.group(group)) is not None
            ).strip()
            if artist and not _is_spotify_result_reference(artist):
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
            if artist and not _is_spotify_result_reference(artist):
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
            if artist and not _is_spotify_result_reference(artist):
                return _request(
                    correlation_id=request_id,
                    action_id=SPOTIFY_PLAY_ARTIST_ACTION,
                    parameters={
                        "service": "spotify",
                        "artist_query": artist,
                    },
                )

        favorites_match = _SPOTIFY_FAVORITES_PATTERN.fullmatch(normalized)
        if favorites_match is not None:
            slash_mode = favorites_match.group("slash")
            favorite_mode = (
                "liked"
                if favorites_match.group("liked")
                or (slash_mode is not None and slash_mode.casefold() == "liked")
                else "mix"
            )
            return _request(
                correlation_id=request_id,
                action_id=SPOTIFY_PLAY_FAVORITES_ACTION,
                parameters={
                    "service": "spotify",
                    "favorite_mode": favorite_mode,
                },
            )

        track_play_match = _SPOTIFY_TRACK_PLAY_PATTERN.fullmatch(normalized)
        if track_play_match is not None:
            query = _matched_query(
                track_play_match,
                ("slash", "labeled", "on_spotify"),
            )
            track, artist = _split_spotify_title_artist_query(query)
            if (
                track
                and not _is_spotify_result_reference(track)
                and track.casefold()
                not in {
                    "music",
                    "playback",
                    "song",
                    "spotify",
                    "track",
                }
            ):
                parameters = {
                    "service": "spotify",
                    "track_query": track,
                }
                if artist:
                    parameters["artist_query"] = artist
                return _request(
                    correlation_id=request_id,
                    action_id=SPOTIFY_PLAY_TRACK_ACTION,
                    parameters=parameters,
                )

        shuffle_match = _SPOTIFY_SHUFFLE_PATTERN.fullmatch(normalized)
        if shuffle_match is not None:
            if shuffle_match.group("enable"):
                enabled = True
            elif shuffle_match.group("disable"):
                enabled = False
            else:
                raw_state = next(
                    shuffle_match.group(name)
                    for name in ("slash", "post_state", "pre_state", "state")
                    if shuffle_match.group(name) is not None
                )
                enabled = raw_state.casefold() == "on"
            return _request(
                correlation_id=request_id,
                action_id=SPOTIFY_SHUFFLE_ACTION,
                parameters={"service": "spotify", "enabled": enabled},
            )

        repeat_match = _SPOTIFY_REPEAT_PATTERN.fullmatch(normalized)
        if repeat_match is not None:
            if repeat_match.group("disable") or repeat_match.group("turn_off"):
                mode = "off"
            else:
                raw_mode = next(
                    repeat_match.group(name)
                    for name in ("slash", "target", "state")
                    if repeat_match.group(name) is not None
                ).casefold()
                mode = (
                    "track"
                    if raw_mode in {"song", "track"}
                    else "context" if raw_mode in {"album", "playlist"} else raw_mode
                )
            return _request(
                correlation_id=request_id,
                action_id=SPOTIFY_REPEAT_ACTION,
                parameters={"service": "spotify", "mode": mode},
            )

        volume_match = _SPOTIFY_VOLUME_PATTERN.fullmatch(normalized)
        if volume_match is not None:
            if volume_match.group("mute"):
                volume_percent = 0
            else:
                raw_volume = next(
                    volume_match.group(name)
                    for name in ("slash", "spotify_value", "on_spotify_value")
                    if volume_match.group(name) is not None
                )
                volume_percent = _parse_volume_percent(raw_volume)
                if volume_percent is None:
                    return None
            return _request(
                correlation_id=request_id,
                action_id=SPOTIFY_VOLUME_ACTION,
                parameters={
                    "service": "spotify",
                    "volume_percent": volume_percent,
                },
            )

        seek_match = _SPOTIFY_SEEK_PATTERN.fullmatch(normalized)
        if seek_match is not None:
            if seek_match.group("restart"):
                position_seconds = 0
            else:
                raw_position = next(
                    seek_match.group(name)
                    for name in (
                        "slash",
                        "spotify_value",
                        "prefixed_value",
                        "on_spotify_value",
                    )
                    if seek_match.group(name) is not None
                )
                position_seconds = _parse_seek_seconds(raw_position)
                if position_seconds is None:
                    return None
            return _request(
                correlation_id=request_id,
                action_id=SPOTIFY_SEEK_ACTION,
                parameters={
                    "service": "spotify",
                    "position_seconds": position_seconds,
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


def _matched_query(match: re.Match[str], groups: tuple[str, ...]) -> str:
    return next(
        value for group in groups if (value := match.group(group)) is not None
    ).strip()


def _is_spotify_result_reference(value: str) -> bool:
    return _SPOTIFY_RESULT_REFERENCE_PATTERN.fullmatch(value.strip()) is not None


def _split_spotify_title_artist_query(query: str) -> tuple[str, str]:
    normalized = query.strip().rstrip(".!?").strip()
    if "|" in normalized:
        title, artist = normalized.split("|", 1)
        return title.strip(), artist.strip()
    parts = re.split(r"\s+by\s+", normalized, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return normalized, ""


def _parse_volume_percent(value: str) -> int | None:
    normalized = re.sub(
        r"\s*(?:%|percent|per\s+cent)\s*$",
        "",
        value.strip().casefold(),
    )
    return _parse_english_number(normalized)


def _parse_seek_seconds(value: str) -> int | None:
    normalized = value.strip().casefold().rstrip(".!?").strip()
    if normalized.isdigit():
        return int(normalized)

    colon_parts = normalized.split(":")
    if len(colon_parts) in {2, 3} and all(part.isdigit() for part in colon_parts):
        numbers = tuple(int(part) for part in colon_parts)
        if len(numbers) == 2:
            minutes, seconds = numbers
            return minutes * 60 + seconds if seconds < 60 else None
        hours, minutes, seconds = numbers
        if minutes < 60 and seconds < 60:
            return hours * 3600 + minutes * 60 + seconds
        return None

    cleaned = re.sub(r"\band\b", " ", normalized).replace(",", " ")
    part_pattern = re.compile(
        r"(?P<value>\d+|[a-z]+(?:[\s-]+[a-z]+)?)\s+"
        r"(?P<unit>hours?|minutes?|seconds?)",
        re.IGNORECASE,
    )
    units: dict[str, int] = {}
    cursor = 0
    for match in part_pattern.finditer(cleaned):
        if cleaned[cursor : match.start()].strip():
            return None
        amount = _parse_english_number(match.group("value"))
        unit = match.group("unit").casefold().rstrip("s")
        if amount is None or unit in units:
            return None
        units[unit] = amount
        cursor = match.end()
    if cleaned[cursor:].strip() or not units:
        return None
    return (
        units.get("hour", 0) * 3600
        + units.get("minute", 0) * 60
        + units.get("second", 0)
    )


def _parse_english_number(value: str) -> int | None:
    normalized = value.strip().casefold()
    if normalized.isdigit():
        return int(normalized)
    words = normalized.replace("-", " ").split()
    if words == ["one", "hundred"]:
        return 100
    if len(words) == 1:
        return _SMALL_NUMBER_WORDS.get(words[0], _TENS_NUMBER_WORDS.get(words[0]))
    if len(words) == 2 and words[0] in _TENS_NUMBER_WORDS:
        unit = _SMALL_NUMBER_WORDS.get(words[1])
        if unit is not None and 1 <= unit <= 9:
            return _TENS_NUMBER_WORDS[words[0]] + unit
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
        unwrapped = _VOICE_TRAILING_NAME_PATTERN.sub("", unwrapped, count=1).strip()
        if unwrapped == normalized:
            break
        normalized = unwrapped
    return _VOICE_SPOTIFY_ALIAS_PATTERN.sub("Spotify", normalized)
