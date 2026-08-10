"""Provider-neutral schemas for explicitly exposed assistant actions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from project_akiha.core.actions.errors import ActionValidationError
from project_akiha.core.actions.models import (
    ActionDefinition,
    ActionFailureCategory,
    ActionRisk,
    ParameterKind,
)
from project_akiha.core.actions.registry import (
    CLOSE_APPLICATION_ACTION,
    DIRECTORY_SEARCH_ACTION,
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
    ActionRegistry,
    build_default_action_registry,
)

# This is intentionally separate from ActionRegistry. Registering a future
# executor must not silently make it available to an AI provider.
DEFAULT_PROVIDER_ACTION_IDS = (
    FILE_SEARCH_ACTION,
    DIRECTORY_SEARCH_ACTION,
    OPEN_DIRECTORY_ACTION,
    OPEN_FILE_ACTION,
    LAUNCH_APPLICATION_ACTION,
    CLOSE_APPLICATION_ACTION,
    SPOTIFY_PLAY_ACTION,
    SPOTIFY_PAUSE_ACTION,
    SPOTIFY_RESUME_ACTION,
    SPOTIFY_NEXT_ACTION,
    SPOTIFY_PREVIOUS_ACTION,
    SPOTIFY_SHUFFLE_ACTION,
    SPOTIFY_REPEAT_ACTION,
    SPOTIFY_VOLUME_ACTION,
    SPOTIFY_SEEK_ACTION,
    SPOTIFY_SEARCH_ARTISTS_ACTION,
    SPOTIFY_OPEN_ARTIST_ACTION,
    SPOTIFY_PLAY_ARTIST_ACTION,
    SPOTIFY_SEARCH_TRACKS_ACTION,
    SPOTIFY_PLAY_TRACK_ACTION,
    SPOTIFY_SEARCH_ALBUMS_ACTION,
    SPOTIFY_OPEN_ALBUM_ACTION,
    SPOTIFY_PLAY_ALBUM_ACTION,
    SPOTIFY_SEARCH_PLAYLISTS_ACTION,
    SPOTIFY_PLAY_PLAYLIST_ACTION,
    SPOTIFY_PLAY_FAVORITES_ACTION,
)


@dataclass(frozen=True, slots=True)
class ActionToolParameterSchema:
    """One primitive parameter safe to describe to an intent provider."""

    name: str
    kind: ParameterKind
    required: bool
    max_length: int | None
    allowed_values: tuple[str, ...]
    minimum_value: int | None
    maximum_value: int | None


@dataclass(frozen=True, slots=True)
class ActionToolSchema:
    """Provider-neutral action shape without executor or permission access."""

    action_id: str
    description: str
    parameters: tuple[ActionToolParameterSchema, ...]


class ProviderActionToolCatalog:
    """Expose only explicitly opted-in registered actions to providers."""

    def __init__(
        self,
        registry: ActionRegistry,
        action_ids: Iterable[str],
    ) -> None:
        schemas: list[ActionToolSchema] = []
        entries: dict[str, ActionToolSchema] = {}
        for action_id in action_ids:
            if action_id in entries:
                raise ValueError(f"duplicate provider action schema: {action_id}")
            definition = registry.resolve(action_id)
            if definition.risk is ActionRisk.PROHIBITED:
                raise ValueError("prohibited actions cannot be exposed to providers.")
            schema = _to_tool_schema(definition)
            entries[action_id] = schema
            schemas.append(schema)
        self._schemas = tuple(schemas)
        self._entries = entries

    @property
    def schemas(self) -> tuple[ActionToolSchema, ...]:
        """Return immutable schemas in stable explicit allowlist order."""
        return self._schemas

    def resolve(self, action_id: str) -> ActionToolSchema:
        """Resolve only an action exposed by this provider catalog."""
        try:
            return self._entries[action_id]
        except KeyError as error:
            raise ActionValidationError(
                ActionFailureCategory.UNKNOWN_ACTION,
                "The proposed provider action is not exposed.",
            ) from error


def build_default_provider_action_catalog(
    registry: ActionRegistry | None = None,
) -> ProviderActionToolCatalog:
    """Build the explicit provider catalog without enabling execution."""
    return ProviderActionToolCatalog(
        registry or build_default_action_registry(),
        DEFAULT_PROVIDER_ACTION_IDS,
    )


def _to_tool_schema(definition: ActionDefinition) -> ActionToolSchema:
    return ActionToolSchema(
        action_id=definition.action_id,
        description=definition.description,
        parameters=tuple(
            ActionToolParameterSchema(
                name=parameter.name,
                kind=parameter.kind,
                required=parameter.required,
                max_length=parameter.max_length,
                allowed_values=parameter.allowed_values,
                minimum_value=parameter.minimum_value,
                maximum_value=parameter.maximum_value,
            )
            for parameter in definition.parameters
        ),
    )
