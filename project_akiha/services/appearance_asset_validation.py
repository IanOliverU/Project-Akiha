"""Offline validation for complete trusted Akiha appearance sets."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from project_akiha.core.appearance import (
    AppearanceApproval,
    AppearanceId,
    AppearanceRegistry,
    load_appearance_approval,
)
from project_akiha.core.state.animation import AnimationState
from project_akiha.providers.animation import (
    AnimationManifestError,
    AssetAnimationProvider,
)

_EXPECTED_FRAME_SIZE = (100, 100)
_REQUIRED_STATES = frozenset(
    {
        AnimationState.IDLE,
        AnimationState.WALKING,
        AnimationState.DRAGGING,
        AnimationState.SLEEPING,
    }
)


class AppearanceAssetIssueCode(StrEnum):
    """Closed, privacy-safe validation failures."""

    APPEARANCE_UNAVAILABLE = "appearance_unavailable"
    MANIFEST_INVALID = "manifest_invalid"
    MISSING_STATE = "missing_state"
    SCALE_UNSUPPORTED = "scale_unsupported"
    IMAGE_UNREADABLE = "image_unreadable"
    IMAGE_MODE_INVALID = "image_mode_invalid"
    FRAME_SIZE_INVALID = "frame_size_invalid"
    SOURCE_RECT_INVALID = "source_rect_invalid"
    ALPHA_INVALID = "alpha_invalid"
    APPROVAL_MISSING = "approval_missing"
    APPROVAL_MISMATCH = "approval_mismatch"


@dataclass(frozen=True, slots=True)
class AppearanceAssetIssue:
    """One bounded validation result without raw image contents."""

    code: AppearanceAssetIssueCode
    state: AnimationState | None = None
    asset_name: str | None = None


@dataclass(frozen=True, slots=True)
class AppearanceAssetReport:
    """Technical and owner-approval readiness for one complete manifest."""

    appearance_id: AppearanceId
    manifest_path: Path
    available_states: frozenset[AnimationState]
    unique_asset_count: int
    declared_frame_count: int
    issues: tuple[AppearanceAssetIssue, ...]
    approval_present: bool
    approval_matches: bool

    @property
    def technically_valid(self) -> bool:
        """Return whether image and manifest checks passed."""
        technical_codes = {
            AppearanceAssetIssueCode.MANIFEST_INVALID,
            AppearanceAssetIssueCode.MISSING_STATE,
            AppearanceAssetIssueCode.SCALE_UNSUPPORTED,
            AppearanceAssetIssueCode.IMAGE_UNREADABLE,
            AppearanceAssetIssueCode.IMAGE_MODE_INVALID,
            AppearanceAssetIssueCode.FRAME_SIZE_INVALID,
            AppearanceAssetIssueCode.SOURCE_RECT_INVALID,
            AppearanceAssetIssueCode.ALPHA_INVALID,
        }
        return not any(issue.code in technical_codes for issue in self.issues)

    @property
    def activation_ready(self) -> bool:
        """Return whether the complete set is technically valid and approved."""
        return self.technically_valid and self.approval_matches


def validate_registered_appearance(
    registry: AppearanceRegistry,
    appearance_id: AppearanceId,
) -> AppearanceAssetReport:
    """Validate one active registry entry and its checked-in approval."""
    if not isinstance(registry, AppearanceRegistry):
        raise TypeError("registry must be an AppearanceRegistry value.")
    if not isinstance(appearance_id, AppearanceId):
        raise TypeError("appearance_id must be an AppearanceId value.")
    manifest_path = registry.manifest_path(appearance_id)
    approval_path = registry.approval_path(appearance_id)
    if manifest_path is None:
        return AppearanceAssetReport(
            appearance_id=appearance_id,
            manifest_path=registry.root / "unavailable.toml",
            available_states=frozenset(),
            unique_asset_count=0,
            declared_frame_count=0,
            issues=(
                AppearanceAssetIssue(AppearanceAssetIssueCode.APPEARANCE_UNAVAILABLE),
            ),
            approval_present=False,
            approval_matches=False,
        )
    approval = (
        load_appearance_approval(approval_path) if approval_path is not None else None
    )
    return validate_appearance_manifest(
        appearance_id,
        manifest_path,
        approval=approval,
        approval_root=registry.root,
    )


def validate_appearance_manifest(
    appearance_id: AppearanceId,
    manifest_path: Path,
    *,
    approval: AppearanceApproval | None = None,
    approval_root: Path | None = None,
) -> AppearanceAssetReport:
    """Validate one complete candidate without activating or modifying it."""
    if not isinstance(appearance_id, AppearanceId):
        raise TypeError("appearance_id must be an AppearanceId value.")
    if not isinstance(manifest_path, Path):
        raise TypeError("manifest_path must be a Path value.")
    if approval is not None and not isinstance(approval, AppearanceApproval):
        raise TypeError("approval must be an AppearanceApproval value or None.")
    if approval_root is not None and not isinstance(approval_root, Path):
        raise TypeError("approval_root must be a Path value or None.")

    issues: list[AppearanceAssetIssue] = []
    try:
        provider = AssetAnimationProvider.from_manifest(manifest_path)
    except AnimationManifestError:
        return AppearanceAssetReport(
            appearance_id,
            manifest_path,
            frozenset(),
            0,
            0,
            (AppearanceAssetIssue(AppearanceAssetIssueCode.MANIFEST_INVALID),),
            approval is not None,
            False,
        )

    states = provider.available_states()
    for state in sorted(_REQUIRED_STATES - states, key=lambda item: item.value):
        issues.append(
            AppearanceAssetIssue(AppearanceAssetIssueCode.MISSING_STATE, state)
        )

    assets: dict[Path, tuple[int, int]] = {}
    frame_count = 0
    for clip in provider.clips_for_review():
        state = clip.state
        frame_count += len(clip.frame_paths)
        if clip.scale_percent != 100:
            issues.append(
                AppearanceAssetIssue(
                    AppearanceAssetIssueCode.SCALE_UNSUPPORTED,
                    state,
                )
            )
        for index, path in enumerate(clip.frame_paths):
            expected = _EXPECTED_FRAME_SIZE
            source_rect = clip.source_rects[index] if clip.source_rects else None
            if source_rect is not None:
                expected = (source_rect[2], source_rect[3])
                if expected != _EXPECTED_FRAME_SIZE:
                    issues.append(
                        AppearanceAssetIssue(
                            AppearanceAssetIssueCode.FRAME_SIZE_INVALID,
                            state,
                            path.name,
                        )
                    )
            assets[path] = expected

    image_metadata: dict[Path, tuple[int, int]] = {}
    for path, expected_frame_size in assets.items():
        image = _open_image(path, issues)
        if image is None:
            continue
        image_metadata[path] = image.size
        if image.mode != "RGBA":
            issues.append(
                AppearanceAssetIssue(
                    AppearanceAssetIssueCode.IMAGE_MODE_INVALID,
                    asset_name=path.name,
                )
            )
            continue
        alpha_values = set(image.getchannel("A").get_flattened_data())
        if (
            not alpha_values
            or not alpha_values.issubset({0, 255})
            or 0 not in alpha_values
        ):
            issues.append(
                AppearanceAssetIssue(
                    AppearanceAssetIssueCode.ALPHA_INVALID,
                    asset_name=path.name,
                )
            )
        if expected_frame_size == _EXPECTED_FRAME_SIZE and not _frame_geometry_valid(
            provider,
            path,
            image.size,
        ):
            issues.append(
                AppearanceAssetIssue(
                    AppearanceAssetIssueCode.SOURCE_RECT_INVALID,
                    asset_name=path.name,
                )
            )

    approval_matches = _approval_matches(
        appearance_id,
        manifest_path,
        image_metadata,
        approval,
        approval_root,
    )
    if approval is None:
        issues.append(AppearanceAssetIssue(AppearanceAssetIssueCode.APPROVAL_MISSING))
    elif not approval_matches:
        issues.append(AppearanceAssetIssue(AppearanceAssetIssueCode.APPROVAL_MISMATCH))

    return AppearanceAssetReport(
        appearance_id=appearance_id,
        manifest_path=manifest_path,
        available_states=states,
        unique_asset_count=len(assets),
        declared_frame_count=frame_count,
        issues=tuple(issues),
        approval_present=approval is not None,
        approval_matches=approval_matches,
    )


def _open_image(path: Path, issues: list[AppearanceAssetIssue]):
    try:
        from PIL import Image

        with Image.open(path) as source:
            image = source.copy()
        return image
    except (ImportError, OSError):
        issues.append(
            AppearanceAssetIssue(
                AppearanceAssetIssueCode.IMAGE_UNREADABLE,
                asset_name=path.name,
            )
        )
        return None


def _frame_geometry_valid(
    provider: AssetAnimationProvider,
    path: Path,
    image_size: tuple[int, int],
) -> bool:
    found = False
    for clip in provider.clips_for_review():
        for index, frame_path in enumerate(clip.frame_paths):
            if frame_path != path:
                continue
            found = True
            if clip.source_rects:
                x, y, width, height = clip.source_rects[index]  # type: ignore[misc]
                if (
                    width != _EXPECTED_FRAME_SIZE[0]
                    or height != _EXPECTED_FRAME_SIZE[1]
                    or x < 0
                    or y < 0
                    or x + width > image_size[0]
                    or y + height > image_size[1]
                ):
                    return False
            elif image_size != _EXPECTED_FRAME_SIZE:
                return False
    return found


def _approval_matches(
    appearance_id: AppearanceId,
    manifest_path: Path,
    image_metadata: dict[Path, tuple[int, int]],
    approval: AppearanceApproval | None,
    approval_root: Path | None,
) -> bool:
    if approval is None or approval_root is None:
        return False
    if approval.appearance_id is not appearance_id:
        return False
    if _sha256(manifest_path) != approval.manifest_sha256:
        return False
    root = approval_root.resolve()
    actual = {
        path.resolve()
        .relative_to(root)
        .as_posix(): (
            _sha256(path),
            dimensions,
        )
        for path, dimensions in image_metadata.items()
        if root in path.resolve().parents
    }
    expected = {
        asset.relative_path: (asset.sha256, (asset.width, asset.height))
        for asset in approval.approved_assets
    }
    return actual == expected


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
