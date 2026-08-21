"""Framework-free contracts for complete trusted Akiha appearances."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath


class AppearanceId(StrEnum):
    """Closed canonical appearance identities supported by Project Akiha."""

    SEIFUKU = "seifuku"
    DRESS = "dress"
    VERMILLION = "vermillion"


class AppearanceAvailability(StrEnum):
    """Whether one complete appearance set is approved for runtime use."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class AppearanceSelectionDecision(StrEnum):
    """Closed outcomes for one explicit appearance-selection request."""

    SELECTED = "selected"
    ALREADY_SELECTED = "already_selected"
    UNAVAILABLE = "unavailable"
    NOT_OWNED = "not_owned"


@dataclass(frozen=True, slots=True)
class AppearanceDefinition:
    """One trusted complete animation set, never an assembled wardrobe."""

    appearance_id: AppearanceId
    display_name: str
    availability: AppearanceAvailability
    manifest_relative_path: str | None = None
    required_item_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.appearance_id, AppearanceId):
            raise TypeError("appearance_id must be an AppearanceId value.")
        if not isinstance(self.display_name, str):
            raise TypeError("display_name must be a string.")
        if not self.display_name or self.display_name != self.display_name.strip():
            raise ValueError("display_name must be nonempty without edge whitespace.")
        if not isinstance(self.availability, AppearanceAvailability):
            raise TypeError("availability must be an AppearanceAvailability value.")
        if self.availability is AppearanceAvailability.AVAILABLE:
            _require_manifest_path(self.manifest_relative_path)
        elif self.manifest_relative_path is not None:
            raise ValueError("unavailable appearances cannot expose a manifest path.")
        if self.required_item_id is not None:
            _require_item_id(self.required_item_id)
        if self.appearance_id is AppearanceId.SEIFUKU:
            if self.required_item_id is not None:
                raise ValueError(
                    "the canonical Seifuku appearance is always available."
                )
            if self.availability is not AppearanceAvailability.AVAILABLE:
                raise ValueError("the canonical Seifuku appearance must be available.")


@dataclass(frozen=True, slots=True)
class AppearanceSelection:
    """Durable singleton selection for one complete appearance."""

    appearance_id: AppearanceId
    selected_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.appearance_id, AppearanceId):
            raise TypeError("appearance_id must be an AppearanceId value.")
        _require_aware_datetime(self.selected_at, "selected_at")


@dataclass(frozen=True, slots=True)
class AppearanceView:
    """Sanitized appearance state for application and UI presentation."""

    appearance_id: AppearanceId
    display_name: str
    availability: AppearanceAvailability
    owned: bool
    selected: bool


@dataclass(frozen=True, slots=True)
class AppearanceSelectionOutcome:
    """Typed result of selecting one complete appearance."""

    decision: AppearanceSelectionDecision
    selection: AppearanceSelection
    requested_appearance_id: AppearanceId


@dataclass(frozen=True, slots=True)
class AppearanceRegistry:
    """Immutable trusted mapping from appearance IDs to whole manifests."""

    root: Path
    default_appearance_id: AppearanceId
    definitions: tuple[AppearanceDefinition, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path):
            raise TypeError("appearance registry root must be a Path value.")
        if not isinstance(self.default_appearance_id, AppearanceId):
            raise TypeError("default_appearance_id must be an AppearanceId value.")
        if not isinstance(self.definitions, tuple) or any(
            not isinstance(item, AppearanceDefinition) for item in self.definitions
        ):
            raise TypeError("definitions must contain AppearanceDefinition values.")
        ids = tuple(item.appearance_id for item in self.definitions)
        if len(ids) != len(set(ids)):
            raise ValueError("appearance registry IDs must be unique.")
        if frozenset(ids) != frozenset(AppearanceId):
            raise ValueError(
                "appearance registry must define all canonical appearances."
            )
        default = self.definition(self.default_appearance_id)
        if default.availability is not AppearanceAvailability.AVAILABLE:
            raise ValueError("the default appearance must be available.")

    def definition(self, appearance_id: AppearanceId) -> AppearanceDefinition:
        """Return one known canonical definition."""
        if not isinstance(appearance_id, AppearanceId):
            raise TypeError("appearance_id must be an AppearanceId value.")
        return next(
            item for item in self.definitions if item.appearance_id is appearance_id
        )

    def manifest_path(self, appearance_id: AppearanceId) -> Path | None:
        """Resolve one approved manifest within the trusted registry root."""
        definition = self.definition(appearance_id)
        relative = definition.manifest_relative_path
        if relative is None:
            return None
        resolved_root = self.root.resolve()
        candidate = (resolved_root / Path(*PurePosixPath(relative).parts)).resolve()
        if candidate != resolved_root and resolved_root not in candidate.parents:
            raise ValueError("appearance manifest escaped the trusted registry root.")
        return candidate


def _require_manifest_path(value: object) -> None:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("appearance manifest must be a trusted relative path.")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.suffix.lower() != ".toml"
    ):
        raise ValueError("appearance manifest must be a normalized relative TOML path.")


def _require_item_id(value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("required_item_id must be a nonempty stable identifier.")


def _require_aware_datetime(value: object, label: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")
