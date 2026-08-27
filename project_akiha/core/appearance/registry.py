"""Strict loading for the fixed trusted appearance registry."""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

from project_akiha.core.appearance.models import (
    AppearanceApproval,
    AppearanceAvailability,
    AppearanceDefinition,
    AppearanceId,
    AppearanceRegistry,
    ApprovedAppearanceAsset,
)

APPEARANCE_REGISTRY_SCHEMA_VERSION = 1
_ROOT_KEYS = frozenset({"schema_version", "default_appearance", "appearances"})
_REQUIRED_KEYS = frozenset({"appearance_id", "display_name", "availability"})
_OPTIONAL_KEYS = frozenset({"manifest", "approval", "required_item_id"})
_APPROVAL_ROOT_KEYS = frozenset(
    {"schema_version", "appearance_id", "manifest_sha256", "assets"}
)
_APPROVAL_ASSET_KEYS = frozenset({"path", "sha256", "width", "height"})


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
        approval_path = registry.approval_path(definition.appearance_id)
        if approval_path is not None:
            approval = load_appearance_approval(approval_path)
            _verify_approval(registry, definition, approval)
    return registry


def load_appearance_approval(path: Path) -> AppearanceApproval:
    """Load one immutable owner-approval record without image dependencies."""
    if not isinstance(path, Path):
        raise TypeError("appearance approval path must be a Path value.")
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise AppearanceRegistryError("Unable to load appearance approval.") from error
    _require_closed_table(
        document,
        _APPROVAL_ROOT_KEYS,
        _APPROVAL_ROOT_KEYS,
        "appearance approval",
    )
    if document["schema_version"] != 1:
        raise AppearanceRegistryError("Unsupported appearance approval schema.")
    assets = document["assets"]
    if not isinstance(assets, list) or any(
        not isinstance(item, dict) for item in assets
    ):
        raise AppearanceRegistryError("approval assets must be an array of tables.")
    try:
        return AppearanceApproval(
            appearance_id=AppearanceId(document["appearance_id"]),
            manifest_sha256=document["manifest_sha256"],
            approved_assets=tuple(_parse_approved_asset(item) for item in assets),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AppearanceRegistryError("Appearance approval is invalid.") from error


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
        approval_relative_path=data.get("approval"),
        required_item_id=data.get("required_item_id"),
    )


def _parse_approved_asset(data: dict[str, Any]) -> ApprovedAppearanceAsset:
    _require_closed_table(
        data,
        _APPROVAL_ASSET_KEYS,
        _APPROVAL_ASSET_KEYS,
        "approved asset",
    )
    return ApprovedAppearanceAsset(
        relative_path=data["path"],
        sha256=data["sha256"],
        width=data["width"],
        height=data["height"],
    )


def _verify_approval(
    registry: AppearanceRegistry,
    definition: AppearanceDefinition,
    approval: AppearanceApproval,
) -> None:
    if approval.appearance_id is not definition.appearance_id:
        raise AppearanceRegistryError("Appearance approval identity does not match.")
    manifest_path = registry.manifest_path(definition.appearance_id)
    if manifest_path is None or _sha256(manifest_path) != approval.manifest_sha256:
        raise AppearanceRegistryError(
            "Appearance manifest approval hash does not match."
        )
    approved_root = registry.root.resolve()
    approved_paths = frozenset(
        asset.relative_path for asset in approval.approved_assets
    )
    if approved_paths != _manifest_asset_paths(manifest_path, approved_root):
        raise AppearanceRegistryError(
            "Appearance approval does not match the manifest asset set."
        )
    for asset in approval.approved_assets:
        candidate = (
            approved_root / Path(*PurePosixPath(asset.relative_path).parts)
        ).resolve()
        if approved_root not in candidate.parents or not candidate.is_file():
            raise AppearanceRegistryError("An approved appearance asset is missing.")
        if _sha256(candidate) != asset.sha256:
            raise AppearanceRegistryError("An approved appearance asset hash changed.")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_asset_paths(manifest_path: Path, approved_root: Path) -> frozenset[str]:
    try:
        document = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise AppearanceRegistryError(
            "Unable to inspect appearance manifest."
        ) from error
    animations = document.get("animations")
    if not isinstance(animations, dict) or not animations:
        raise AppearanceRegistryError("Appearance manifest has no animations.")
    clips = document.get("clips", {})
    if not isinstance(clips, dict):
        raise AppearanceRegistryError("Appearance manifest clips are invalid.")
    paths: set[str] = set()
    for clip in (*animations.values(), *clips.values()):
        if not isinstance(clip, dict):
            raise AppearanceRegistryError("Appearance manifest clip is invalid.")
        values = clip.get("frames")
        if values is None:
            values = [clip.get("filmstrip")]
        if not isinstance(values, list) or any(
            not isinstance(value, str) for value in values
        ):
            raise AppearanceRegistryError("Appearance manifest assets are invalid.")
        for value in values:
            if "\\" in value or ":" in value:
                raise AppearanceRegistryError(
                    "Appearance manifest asset path is unsafe."
                )
            relative = PurePosixPath(value)
            if (
                relative.is_absolute()
                or relative.as_posix() != value
                or any(part in {"", ".", ".."} for part in relative.parts)
                or relative.suffix.lower() != ".png"
            ):
                raise AppearanceRegistryError(
                    "Appearance manifest asset path is unsafe."
                )
            candidate = (manifest_path.parent / Path(*relative.parts)).resolve()
            if approved_root not in candidate.parents:
                raise AppearanceRegistryError(
                    "Appearance manifest asset escaped the trusted root."
                )
            paths.add(candidate.relative_to(approved_root).as_posix())
    return frozenset(paths)


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
