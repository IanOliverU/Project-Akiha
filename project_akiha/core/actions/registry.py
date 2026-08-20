"""Application-owned allowlist of assistant actions."""

from __future__ import annotations

from collections.abc import Iterable

from project_akiha.core.actions.errors import ActionValidationError
from project_akiha.core.actions.models import (
    ActionDefinition,
    ActionFailureCategory,
    ActionParameterSpec,
    ActionRisk,
    ConfirmationPolicy,
    ParameterKind,
)

FILE_SEARCH_ACTION = "files.search"
DIRECTORY_SEARCH_ACTION = "directories.search"
OPEN_DIRECTORY_ACTION = "files.open_directory"
OPEN_FILE_ACTION = "files.open"
LAUNCH_APPLICATION_ACTION = "applications.launch"
CLOSE_APPLICATION_ACTION = "applications.close"
SPOTIFY_PLAY_ACTION = "spotify.play"
SPOTIFY_PLAY_ARTIST_ACTION = "spotify.play_artist"
SPOTIFY_OPEN_ARTIST_ACTION = "spotify.open_artist"
SPOTIFY_PAUSE_ACTION = "spotify.pause"
SPOTIFY_RESUME_ACTION = "spotify.resume"
SPOTIFY_NEXT_ACTION = "spotify.next"
SPOTIFY_PREVIOUS_ACTION = "spotify.previous"
SPOTIFY_CURRENT_PLAYBACK_ACTION = "spotify.current_playback"
SPOTIFY_SHUFFLE_ACTION = "spotify.shuffle"
SPOTIFY_REPEAT_ACTION = "spotify.repeat"
SPOTIFY_VOLUME_ACTION = "spotify.volume"
SPOTIFY_SEEK_ACTION = "spotify.seek"
SPOTIFY_SEARCH_PLAYLISTS_ACTION = "spotify.search_playlists"
SPOTIFY_PLAY_PLAYLIST_ACTION = "spotify.play_playlist"
SPOTIFY_PLAY_FAVORITES_ACTION = "spotify.play_favorites"
SPOTIFY_SEARCH_ARTISTS_ACTION = "spotify.search_artists"
SPOTIFY_SEARCH_TRACKS_ACTION = "spotify.search_tracks"
SPOTIFY_PLAY_TRACK_ACTION = "spotify.play_track"
SPOTIFY_SEARCH_ALBUMS_ACTION = "spotify.search_albums"
SPOTIFY_OPEN_ALBUM_ACTION = "spotify.open_album"
SPOTIFY_PLAY_ALBUM_ACTION = "spotify.play_album"

FILE_SEARCH_CAPABILITY = "files.search"
FILE_OPEN_CAPABILITY = "files.open"
APPLICATION_LAUNCH_CAPABILITY = "applications.launch"
APPLICATION_CLOSE_CAPABILITY = "applications.close"
SPOTIFY_PLAYBACK_CAPABILITY = "spotify.playback"

ALLOWLISTED_APPLICATION_IDS = ("chrome", "discord", "spotify", "vlc", "vscode")


class ActionRegistry:
    """Resolve only action definitions registered by the application."""

    def __init__(self, definitions: Iterable[ActionDefinition]) -> None:
        entries: dict[str, ActionDefinition] = {}
        for definition in definitions:
            if definition.action_id in entries:
                raise ValueError(f"duplicate action definition: {definition.action_id}")
            entries[definition.action_id] = definition
        self._entries = entries

    @property
    def definitions(self) -> tuple[ActionDefinition, ...]:
        """Return registered definitions in stable insertion order."""
        return tuple(self._entries.values())

    def resolve(self, action_id: str) -> ActionDefinition:
        """Return one definition or reject the unknown identifier."""
        try:
            return self._entries[action_id]
        except KeyError as error:
            raise ActionValidationError(
                ActionFailureCategory.UNKNOWN_ACTION,
                "The requested assistant action is not registered.",
            ) from error


def build_default_action_registry() -> ActionRegistry:
    """Build the Phase 8 allowlist without enabling any executors."""
    return ActionRegistry(
        (
            ActionDefinition(
                action_id=FILE_SEARCH_ACTION,
                description=(
                    "Search file names inside an approved root or descendant. "
                    "Use a user-facing root-relative location such as "
                    "Downloads/Video or Desktop/Solitude Freak. For an explicit "
                    "play/open request use result_mode=open_unique; for an "
                    "explicit request to play any matching file use "
                    "result_mode=open_any; otherwise use present. Use a title "
                    "or extension such as Elis or .mp4 as query. Set relaxed "
                    "to true for voice-spoken media titles so related local "
                    "candidates can be shown when no exact title exists. Results are "
                    "handled privately in Akiha's local UI; do not claim "
                    "filesystem access is denied."
                ),
                risk=ActionRisk.READ_ONLY,
                permission_capability=FILE_SEARCH_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="file_search",
                target_parameter="root",
                parameters=(
                    ActionParameterSpec(
                        name="root",
                        kind=ParameterKind.STRING,
                        max_length=1024,
                    ),
                    ActionParameterSpec(
                        name="query",
                        kind=ParameterKind.STRING,
                        max_length=256,
                    ),
                    ActionParameterSpec(
                        name="media_only",
                        kind=ParameterKind.BOOLEAN,
                        required=False,
                    ),
                    ActionParameterSpec(
                        name="result_mode",
                        kind=ParameterKind.STRING,
                        required=False,
                        allowed_values=("present", "open_unique", "open_any"),
                    ),
                    ActionParameterSpec(
                        name="relaxed",
                        kind=ParameterKind.BOOLEAN,
                        required=False,
                    ),
                ),
                timeout_seconds=10,
                max_results=100,
            ),
            ActionDefinition(
                action_id=DIRECTORY_SEARCH_ACTION,
                description=(
                    "Search directory names inside an approved root or "
                    "descendant using a root-relative location such as "
                    "Downloads/Compressed. Results remain in Akiha's local UI."
                ),
                risk=ActionRisk.READ_ONLY,
                permission_capability=FILE_SEARCH_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="directory_search",
                target_parameter="root",
                parameters=(
                    ActionParameterSpec(
                        name="root",
                        kind=ParameterKind.STRING,
                        max_length=1024,
                    ),
                    ActionParameterSpec(
                        name="query",
                        kind=ParameterKind.STRING,
                        max_length=256,
                    ),
                    ActionParameterSpec(
                        name="match_all",
                        kind=ParameterKind.BOOLEAN,
                        required=False,
                    ),
                ),
                timeout_seconds=10,
                max_results=100,
            ),
            ActionDefinition(
                action_id=OPEN_DIRECTORY_ACTION,
                description=(
                    "Open an approved directory or one of its descendants in "
                    "the file browser. Use the user-facing root name, such as "
                    "Downloads, or a root-relative path such as "
                    "Downloads/Videos. After local numbered directory results, "
                    "use the opaque path value result 1, result 2, and so on. "
                    "Do not invent an absolute path."
                ),
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=FILE_OPEN_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="open_directory",
                target_parameter="path",
                parameters=(
                    ActionParameterSpec(
                        name="path",
                        kind=ParameterKind.STRING,
                        max_length=1024,
                    ),
                ),
                timeout_seconds=10,
            ),
            ActionDefinition(
                action_id=OPEN_FILE_ACTION,
                description=(
                    "Open an allowlisted passive file after confirmation. Use "
                    "an approved root-relative path such as "
                    "Downloads/Video/example.mp4. After local numbered media "
                    "results, use the opaque path value result 1, result 2, and "
                    "so on. Never invent an absolute path."
                ),
                risk=ActionRisk.SENSITIVE_OPEN,
                permission_capability=FILE_OPEN_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.ALWAYS,
                executor_id="open_safe_file",
                target_parameter="path",
                parameters=(
                    ActionParameterSpec(
                        name="path",
                        kind=ParameterKind.STRING,
                        max_length=1024,
                    ),
                ),
                timeout_seconds=10,
            ),
            ActionDefinition(
                action_id=LAUNCH_APPLICATION_ACTION,
                description="Launch one explicitly enabled catalog application.",
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=APPLICATION_LAUNCH_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="launch_allowlisted_application",
                target_parameter="application_id",
                parameters=(
                    ActionParameterSpec(
                        name="application_id",
                        kind=ParameterKind.STRING,
                        max_length=64,
                        allowed_values=ALLOWLISTED_APPLICATION_IDS,
                    ),
                ),
                timeout_seconds=10,
            ),
            ActionDefinition(
                action_id=CLOSE_APPLICATION_ACTION,
                description="Gracefully close an explicitly enabled application.",
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=APPLICATION_CLOSE_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="close_allowlisted_application",
                target_parameter="application_id",
                parameters=(
                    ActionParameterSpec(
                        name="application_id",
                        kind=ParameterKind.STRING,
                        max_length=64,
                        allowed_values=ALLOWLISTED_APPLICATION_IDS,
                    ),
                ),
                timeout_seconds=10,
            ),
            *(
                ActionDefinition(
                    action_id=action_id,
                    description=description,
                    risk=ActionRisk.USER_VISIBLE,
                    permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                    confirmation_policy=ConfirmationPolicy.NEVER,
                    executor_id=f"spotify_{control}",
                    target_parameter="service",
                    parameters=(
                        ActionParameterSpec(
                            name="service",
                            kind=ParameterKind.STRING,
                            max_length=16,
                            allowed_values=("spotify",),
                        ),
                    ),
                    timeout_seconds=20,
                )
                for action_id, control, description in (
                    (
                        SPOTIFY_PLAY_ACTION,
                        "play",
                        "Start or resume playback on an approved Spotify device.",
                    ),
                    (
                        SPOTIFY_PAUSE_ACTION,
                        "pause",
                        "Pause playback on an approved Spotify device.",
                    ),
                    (
                        SPOTIFY_RESUME_ACTION,
                        "resume",
                        "Resume playback on an approved Spotify device.",
                    ),
                    (
                        SPOTIFY_NEXT_ACTION,
                        "next",
                        "Skip to the next item on an approved Spotify device.",
                    ),
                    (
                        SPOTIFY_PREVIOUS_ACTION,
                        "previous",
                        "Return to the previous item on an approved Spotify device.",
                    ),
                )
            ),
            ActionDefinition(
                action_id=SPOTIFY_CURRENT_PLAYBACK_ACTION,
                description=(
                    "Read the current Spotify item only when the user explicitly "
                    "asks what song, track, or content is playing. Return only "
                    "bounded title, creator, album, progress, and playing or paused "
                    "metadata. Do not invent playback state or use this action for "
                    "catalog search."
                ),
                risk=ActionRisk.READ_ONLY,
                permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="spotify_current_playback",
                target_parameter="service",
                parameters=(
                    ActionParameterSpec(
                        name="service",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("spotify",),
                    ),
                ),
                timeout_seconds=20,
            ),
            ActionDefinition(
                action_id=SPOTIFY_SHUFFLE_ACTION,
                description="Set shuffle on one approved Spotify device.",
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="spotify_shuffle",
                target_parameter="service",
                parameters=(
                    ActionParameterSpec(
                        name="service",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("spotify",),
                    ),
                    ActionParameterSpec(
                        name="enabled",
                        kind=ParameterKind.BOOLEAN,
                    ),
                ),
                timeout_seconds=20,
            ),
            ActionDefinition(
                action_id=SPOTIFY_REPEAT_ACTION,
                description="Set repeat mode on one approved Spotify device.",
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="spotify_repeat",
                target_parameter="service",
                parameters=(
                    ActionParameterSpec(
                        name="service",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("spotify",),
                    ),
                    ActionParameterSpec(
                        name="mode",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("track", "context", "off"),
                    ),
                ),
                timeout_seconds=20,
            ),
            ActionDefinition(
                action_id=SPOTIFY_VOLUME_ACTION,
                description="Set volume on one supported Spotify device.",
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="spotify_volume",
                target_parameter="service",
                parameters=(
                    ActionParameterSpec(
                        name="service",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("spotify",),
                    ),
                    ActionParameterSpec(
                        name="volume_percent",
                        kind=ParameterKind.INTEGER,
                        required=False,
                        minimum_value=0,
                        maximum_value=100,
                    ),
                    ActionParameterSpec(
                        name="volume_delta_percent",
                        kind=ParameterKind.INTEGER,
                        required=False,
                        minimum_value=-100,
                        maximum_value=100,
                    ),
                ),
                timeout_seconds=20,
            ),
            ActionDefinition(
                action_id=SPOTIFY_SEEK_ACTION,
                description="Seek to a bounded position in Spotify playback.",
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="spotify_seek",
                target_parameter="service",
                parameters=(
                    ActionParameterSpec(
                        name="service",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("spotify",),
                    ),
                    ActionParameterSpec(
                        name="position_seconds",
                        kind=ParameterKind.INTEGER,
                        minimum_value=0,
                        maximum_value=86400,
                    ),
                ),
                timeout_seconds=20,
            ),
            ActionDefinition(
                action_id=SPOTIFY_SEARCH_ARTISTS_ACTION,
                description="Search for artists in the bounded Spotify catalog.",
                risk=ActionRisk.READ_ONLY,
                permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="spotify_search_artists",
                target_parameter="service",
                parameters=(
                    ActionParameterSpec(
                        name="service",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("spotify",),
                    ),
                    ActionParameterSpec(
                        name="artist_query",
                        kind=ParameterKind.STRING,
                        max_length=160,
                    ),
                ),
                timeout_seconds=20,
                max_results=5,
            ),
            ActionDefinition(
                action_id=SPOTIFY_OPEN_ARTIST_ACTION,
                description="Resolve and open an artist's official Spotify page.",
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="spotify_open_artist",
                target_parameter="service",
                parameters=(
                    ActionParameterSpec(
                        name="service",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("spotify",),
                    ),
                    ActionParameterSpec(
                        name="artist_query",
                        kind=ParameterKind.STRING,
                        max_length=160,
                    ),
                    ActionParameterSpec(
                        name="artist_name",
                        kind=ParameterKind.STRING,
                        required=False,
                        max_length=160,
                    ),
                    ActionParameterSpec(
                        name="artist_uri",
                        kind=ParameterKind.STRING,
                        required=False,
                        max_length=256,
                    ),
                ),
                timeout_seconds=20,
                max_results=5,
            ),
            ActionDefinition(
                action_id=SPOTIFY_PLAY_ARTIST_ACTION,
                description="Resolve and play an artist catalog on Spotify.",
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="spotify_play_artist",
                target_parameter="service",
                parameters=(
                    ActionParameterSpec(
                        name="service",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("spotify",),
                    ),
                    ActionParameterSpec(
                        name="artist_query",
                        kind=ParameterKind.STRING,
                        max_length=160,
                    ),
                    ActionParameterSpec(
                        name="artist_name",
                        kind=ParameterKind.STRING,
                        required=False,
                        max_length=160,
                    ),
                    ActionParameterSpec(
                        name="artist_uri",
                        kind=ParameterKind.STRING,
                        required=False,
                        max_length=256,
                    ),
                ),
                timeout_seconds=20,
                max_results=5,
            ),
            ActionDefinition(
                action_id=SPOTIFY_SEARCH_TRACKS_ACTION,
                description=(
                    "Search for tracks in the bounded Spotify catalog. Put only "
                    "the song title in track_query and the performer in "
                    "artist_query. Present numbered results locally when more "
                    "than one version matches."
                ),
                risk=ActionRisk.READ_ONLY,
                permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="spotify_search_tracks",
                target_parameter="service",
                parameters=(
                    ActionParameterSpec(
                        name="service",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("spotify",),
                    ),
                    ActionParameterSpec(
                        name="track_query",
                        kind=ParameterKind.STRING,
                        max_length=160,
                    ),
                    ActionParameterSpec(
                        name="artist_query",
                        kind=ParameterKind.STRING,
                        required=False,
                        max_length=160,
                    ),
                ),
                timeout_seconds=20,
                max_results=5,
            ),
            ActionDefinition(
                action_id=SPOTIFY_PLAY_TRACK_ACTION,
                description=(
                    "Resolve and play one specific Spotify track. Put only the "
                    "song title in track_query and the performer in artist_query. "
                    "After local numbered results, use track_query 'result 1' "
                    "through 'result 5'. Do not claim playback succeeded until "
                    "the returned action status is success."
                ),
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="spotify_play_track",
                target_parameter="service",
                parameters=(
                    ActionParameterSpec(
                        name="service",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("spotify",),
                    ),
                    ActionParameterSpec(
                        name="track_query",
                        kind=ParameterKind.STRING,
                        max_length=160,
                    ),
                    ActionParameterSpec(
                        name="artist_query",
                        kind=ParameterKind.STRING,
                        required=False,
                        max_length=160,
                    ),
                    ActionParameterSpec(
                        name="track_name",
                        kind=ParameterKind.STRING,
                        required=False,
                        max_length=160,
                    ),
                    ActionParameterSpec(
                        name="track_artist",
                        kind=ParameterKind.STRING,
                        required=False,
                        max_length=160,
                    ),
                    ActionParameterSpec(
                        name="track_uri",
                        kind=ParameterKind.STRING,
                        required=False,
                        max_length=256,
                    ),
                ),
                timeout_seconds=20,
                max_results=5,
            ),
            ActionDefinition(
                action_id=SPOTIFY_SEARCH_ALBUMS_ACTION,
                description="Search for albums in the bounded Spotify catalog.",
                risk=ActionRisk.READ_ONLY,
                permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="spotify_search_albums",
                target_parameter="service",
                parameters=(
                    ActionParameterSpec(
                        name="service",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("spotify",),
                    ),
                    ActionParameterSpec(
                        name="album_query",
                        kind=ParameterKind.STRING,
                        max_length=160,
                    ),
                    ActionParameterSpec(
                        name="artist_query",
                        kind=ParameterKind.STRING,
                        required=False,
                        max_length=160,
                    ),
                ),
                timeout_seconds=20,
                max_results=5,
            ),
            *(
                ActionDefinition(
                    action_id=action_id,
                    description=description,
                    risk=ActionRisk.USER_VISIBLE,
                    permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                    confirmation_policy=ConfirmationPolicy.NEVER,
                    executor_id=executor_id,
                    target_parameter="service",
                    parameters=(
                        ActionParameterSpec(
                            name="service",
                            kind=ParameterKind.STRING,
                            max_length=16,
                            allowed_values=("spotify",),
                        ),
                        ActionParameterSpec(
                            name="album_query",
                            kind=ParameterKind.STRING,
                            max_length=160,
                        ),
                        ActionParameterSpec(
                            name="artist_query",
                            kind=ParameterKind.STRING,
                            required=False,
                            max_length=160,
                        ),
                        ActionParameterSpec(
                            name="album_name",
                            kind=ParameterKind.STRING,
                            required=False,
                            max_length=160,
                        ),
                        ActionParameterSpec(
                            name="album_artist",
                            kind=ParameterKind.STRING,
                            required=False,
                            max_length=160,
                        ),
                        ActionParameterSpec(
                            name="album_uri",
                            kind=ParameterKind.STRING,
                            required=False,
                            max_length=256,
                        ),
                    ),
                    timeout_seconds=20,
                    max_results=5,
                )
                for action_id, executor_id, description in (
                    (
                        SPOTIFY_OPEN_ALBUM_ACTION,
                        "spotify_open_album",
                        "Resolve and open an album's official Spotify page.",
                    ),
                    (
                        SPOTIFY_PLAY_ALBUM_ACTION,
                        "spotify_play_album",
                        "Resolve and play one Spotify album.",
                    ),
                )
            ),
            ActionDefinition(
                action_id=SPOTIFY_SEARCH_PLAYLISTS_ACTION,
                description="Search bounded personal and catalog Spotify playlists.",
                risk=ActionRisk.READ_ONLY,
                permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="spotify_search_playlists",
                target_parameter="service",
                parameters=(
                    ActionParameterSpec(
                        name="service",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("spotify",),
                    ),
                    ActionParameterSpec(
                        name="playlist_query",
                        kind=ParameterKind.STRING,
                        max_length=160,
                    ),
                ),
                timeout_seconds=20,
                max_results=5,
            ),
            ActionDefinition(
                action_id=SPOTIFY_PLAY_PLAYLIST_ACTION,
                description="Resolve and play one Spotify playlist.",
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="spotify_play_playlist",
                target_parameter="service",
                parameters=(
                    ActionParameterSpec(
                        name="service",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("spotify",),
                    ),
                    ActionParameterSpec(
                        name="playlist_query",
                        kind=ParameterKind.STRING,
                        max_length=160,
                    ),
                    ActionParameterSpec(
                        name="playlist_name",
                        kind=ParameterKind.STRING,
                        required=False,
                        max_length=160,
                    ),
                    ActionParameterSpec(
                        name="playlist_owner",
                        kind=ParameterKind.STRING,
                        required=False,
                        max_length=160,
                    ),
                    ActionParameterSpec(
                        name="playlist_uri",
                        kind=ParameterKind.STRING,
                        required=False,
                        max_length=256,
                    ),
                ),
                timeout_seconds=20,
                max_results=5,
            ),
            ActionDefinition(
                action_id=SPOTIFY_PLAY_FAVORITES_ACTION,
                description="Play a bounded local queue from Spotify preferences.",
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=SPOTIFY_PLAYBACK_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="spotify_play_favorites",
                target_parameter="service",
                parameters=(
                    ActionParameterSpec(
                        name="service",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("spotify",),
                    ),
                    ActionParameterSpec(
                        name="favorite_mode",
                        kind=ParameterKind.STRING,
                        max_length=16,
                        allowed_values=("liked", "mix"),
                    ),
                ),
                timeout_seconds=30,
                max_results=50,
            ),
        )
    )
