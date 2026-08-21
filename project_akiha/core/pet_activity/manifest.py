"""Strict local loading for trusted autonomous activity definitions."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from project_akiha.core.behavior import ActivityState, CompanionMood
from project_akiha.core.pet_activity.models import (
    PetActivityDefinition,
    PetActivityId,
)
from project_akiha.core.state.animation import AnimationState

PET_ACTIVITY_SCHEMA_VERSION = 1


class PetActivityManifestError(ValueError):
    """Raised when trusted activity data is malformed or incomplete."""


def load_pet_activity_manifest(path: Path) -> tuple[PetActivityDefinition, ...]:
    """Load a complete, closed, provider-independent activity manifest."""
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise PetActivityManifestError(f"Unable to read {path}.") from error
    except tomllib.TOMLDecodeError as error:
        raise PetActivityManifestError(f"Invalid TOML in {path}.") from error

    if set(document) != {"schema_version", "activities"}:
        raise PetActivityManifestError("Activity manifest fields are invalid.")
    if document["schema_version"] != PET_ACTIVITY_SCHEMA_VERSION:
        raise PetActivityManifestError("Unsupported activity manifest schema.")
    activities = document["activities"]
    if not isinstance(activities, list) or not activities:
        raise PetActivityManifestError("activities must be a non-empty array.")

    definitions = tuple(_parse_definition(value) for value in activities)
    identifiers = tuple(value.activity_id for value in definitions)
    if len(set(identifiers)) != len(identifiers):
        raise PetActivityManifestError("Activity IDs must be unique.")
    if set(identifiers) != set(PetActivityId):
        raise PetActivityManifestError("Activity manifest must define every closed ID.")
    return definitions


def _parse_definition(value: Any) -> PetActivityDefinition:
    if not isinstance(value, dict):
        raise PetActivityManifestError("Each activity must be a table.")
    expected = {
        "id",
        "animation_state",
        "duration_seconds",
        "cooldown_seconds",
        "selection_priority",
        "allowed_user_states",
        "allowed_moods",
        "minimum_energy",
        "maximum_energy",
    }
    if set(value) != expected:
        raise PetActivityManifestError("Activity fields are invalid.")
    try:
        return PetActivityDefinition(
            activity_id=PetActivityId(value["id"]),
            animation_state=AnimationState(value["animation_state"]),
            duration_seconds=value["duration_seconds"],
            cooldown_seconds=value["cooldown_seconds"],
            selection_priority=value["selection_priority"],
            allowed_user_states=_enum_set(value["allowed_user_states"], ActivityState),
            allowed_moods=_enum_set(value["allowed_moods"], CompanionMood),
            minimum_energy=value["minimum_energy"],
            maximum_energy=value["maximum_energy"],
        )
    except (TypeError, ValueError) as error:
        raise PetActivityManifestError("Activity values are invalid.") from error


def _enum_set(value: Any, enum_type: Any) -> frozenset[Any]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) for item in value)
    ):
        raise PetActivityManifestError("Activity enum filters must be string arrays.")
    return frozenset(enum_type(item) for item in value)
