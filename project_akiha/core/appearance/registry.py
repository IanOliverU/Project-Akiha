"""Strict loading for the fixed trusted appearance registry."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from project_akiha.core.appearance.models import (
    AppearanceAvailability,
    AppearanceDefinition,
    AppearanceId,
    AppearanceRegistry,
)

APPEARANCE_REGISTRY_SCHEMA_VERSION = 1
_ROOT_KEYS = frozenset({"schema_version", "default_appearance", "appearances"})
_REQUIRED_KEYS = frozenset({"appearance_id", "display_name", "availability"})
_OPTIONAL_KEYS = frozenset({"manifest", "required_item_id"})


class AppearanceRegistryError(ValueError):
    """Raised when trusted appearance metadata is unreadable or invalid."""


def load_appearance_registry(path: Path) -> AppearanceRegistry:
    """Load and validate the closed appearance registry."""
    if not isinstance(path, Path):
        raise TypeError("appearance registry path must be a Path value.")
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise AppearanceRegistryError("Unable to load appearance registry.") from error
    _require_closed_table(document, _ROOT_KEYS, _ROOT_KEYS, "registry")
    if document["schema_version"] != APPEARANCE_REGISTRY_SCHEMA_VERSION:
        raise AppearanceRegistryError("Unsupported appearance registry schema.")
    entries = document["appearances"]
    if not isinstance(entries, list) or any(
        not isinstance(item, dict) for item in entries
    ):
        raise AppearanceRegistryError("appearances must be an array of tables.")
    try:
        definitions = tuple(_parse_definition(item) for item in entries)
        registry = AppearanceRegistry(
            root=path.parent,
            default_appearance_id=AppearanceId(document["default_appearance"]),
            definitions=definitions,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AppearanceRegistryError("Appearance registry is invalid.") from error
    for definition in registry.definitions:
        manifest_path = registry.manifest_path(definition.appearance_id)
        if manifest_path is not None and not manifest_path.is_file():
            raise AppearanceRegistryError(
                "An available appearance manifest is missing."
            )
    return registry


def _parse_definition(data: dict[str, Any]) -> AppearanceDefinition:
    _require_closed_table(
        data,
        _REQUIRED_KEYS,
        _REQUIRED_KEYS | _OPTIONAL_KEYS,
        "appearance",
    )
    return AppearanceDefinition(
        appearance_id=AppearanceId(data["appearance_id"]),
        display_name=data["display_name"],
        availability=AppearanceAvailability(data["availability"]),
        manifest_relative_path=data.get("manifest"),
        required_item_id=data.get("required_item_id"),
    )


def _require_closed_table(
    value: object,
    required: frozenset[str],
    allowed: frozenset[str],
    label: str,
) -> None:
    if not isinstance(value, dict):
        raise AppearanceRegistryError(f"{label} must be a TOML table.")
    keys = frozenset(value)
    if required - keys or keys - allowed:
        raise AppearanceRegistryError(f"{label} contains invalid fields.")
