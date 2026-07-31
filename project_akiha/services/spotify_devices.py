"""Safe, deterministic Spotify device selection and desktop activation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from project_akiha.core.actions import (
    LAUNCH_APPLICATION_ACTION,
    ActionCancellationToken,
    ActionFailureCategory,
    ActionRequest,
    ActionResult,
    ActionStatus,
)
from project_akiha.services.assistant_actions import AssistantActionService
from project_akiha.services.spotify_client import SpotifyAPIError, SpotifyDevice

_SPOTIFY_APPLICATION_ID = "spotify"


class SpotifyDeviceSource(Protocol):
    """Provider of fresh Spotify device snapshots."""

    def get_available_devices(self) -> tuple[SpotifyDevice, ...]: ...


class SpotifyApplicationActivator(Protocol):
    """Permission-gated desktop activation boundary."""

    async def activate(
        self,
        correlation_id: str,
        *,
        cancellation_token: ActionCancellationToken | None = None,
    ) -> ActionResult: ...


class SpotifyDeviceStatus(StrEnum):
    """Bounded outcomes from local Spotify device resolution."""

    READY = "ready"
    NO_DEVICE = "no_device"
    RESTRICTED_ONLY = "restricted_only"
    AMBIGUOUS = "ambiguous"
    APP_PERMISSION_REQUIRED = "app_permission_required"
    APP_UNAVAILABLE = "app_unavailable"
    APP_START_TIMEOUT = "app_start_timeout"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SpotifyDeviceResolution:
    """Privacy-safe result used by later typed playback actions."""

    status: SpotifyDeviceStatus
    selected_device: SpotifyDevice | None = None
    candidate_count: int = 0
    detail: str = ""


class PermissionGatedSpotifyActivator:
    """Launch Spotify exclusively through the Phase 8 action boundary."""

    def __init__(self, action_service: AssistantActionService) -> None:
        self._action_service = action_service

    async def activate(
        self,
        correlation_id: str,
        *,
        cancellation_token: ActionCancellationToken | None = None,
    ) -> ActionResult:
        request = ActionRequest(
            correlation_id=correlation_id,
            action_id=LAUNCH_APPLICATION_ACTION,
            source="spotify",
            parameters={"application_id": _SPOTIFY_APPLICATION_ID},
        )
        return await self._action_service.evaluate_request(
            request,
            confirmed=False,
            cancellation_token=cancellation_token,
        )


class SpotifyDeviceCoordinator:
    """Resolve a device, optionally activating Spotify through user permission."""

    def __init__(
        self,
        device_source: SpotifyDeviceSource,
        activator: SpotifyApplicationActivator,
        *,
        auto_launch_desktop_app: bool = True,
        poll_attempts: int = 5,
        poll_interval_seconds: float = 1.0,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not 1 <= poll_attempts <= 30:
            raise ValueError("Spotify device poll attempts must be between 1 and 30.")
        if not 0 <= poll_interval_seconds <= 10:
            raise ValueError("Spotify device poll interval must be between 0 and 10.")
        self._device_source = device_source
        self._activator = activator
        self._auto_launch_desktop_app = auto_launch_desktop_app
        self._poll_attempts = poll_attempts
        self._poll_interval_seconds = poll_interval_seconds
        self._sleeper = sleeper

    def apply_auto_launch(self, enabled: bool) -> None:
        """Apply the public launch preference to future resolutions."""
        self._auto_launch_desktop_app = bool(enabled)

    async def resolve(
        self,
        correlation_id: str,
        *,
        cancellation_token: ActionCancellationToken | None = None,
    ) -> SpotifyDeviceResolution:
        """Return a fresh playback target without persisting its device ID."""
        if _is_cancelled(cancellation_token):
            return _cancelled_resolution()
        initial = await self._load_and_select()
        if initial.status not in {
            SpotifyDeviceStatus.NO_DEVICE,
            SpotifyDeviceStatus.RESTRICTED_ONLY,
        }:
            return initial
        if not self._auto_launch_desktop_app:
            return initial

        launch = await self._activator.activate(
            correlation_id,
            cancellation_token=cancellation_token,
        )
        if launch.status is ActionStatus.CANCELLED or _is_cancelled(cancellation_token):
            return _cancelled_resolution()
        if launch.status is not ActionStatus.SUCCESS:
            return _launch_failure_resolution(launch)

        for _ in range(self._poll_attempts):
            await self._sleeper(self._poll_interval_seconds)
            if _is_cancelled(cancellation_token):
                return _cancelled_resolution()
            current = await self._load_and_select()
            if current.status is not SpotifyDeviceStatus.NO_DEVICE:
                return current
        return SpotifyDeviceResolution(
            status=SpotifyDeviceStatus.APP_START_TIMEOUT,
            detail="Spotify started, but no controllable device became available.",
        )

    async def _load_and_select(self) -> SpotifyDeviceResolution:
        try:
            devices = await asyncio.to_thread(self._device_source.get_available_devices)
        except SpotifyAPIError:
            return SpotifyDeviceResolution(
                status=SpotifyDeviceStatus.FAILED,
                detail="Spotify devices could not be checked.",
            )
        return select_spotify_device(devices)


def select_spotify_device(
    devices: Sequence[SpotifyDevice],
) -> SpotifyDeviceResolution:
    """Select an active device, then an unambiguous desktop or sole device."""
    usable = tuple(device for device in devices if not device.is_restricted)
    active = tuple(device for device in usable if device.is_active)
    if len(active) == 1:
        return _ready_resolution(active[0], usable)
    if len(active) > 1:
        return SpotifyDeviceResolution(
            status=SpotifyDeviceStatus.AMBIGUOUS,
            candidate_count=len(active),
            detail="Multiple active Spotify devices are available.",
        )

    computers = tuple(
        device for device in usable if device.device_type.casefold() == "computer"
    )
    if len(computers) == 1:
        return _ready_resolution(computers[0], usable)
    if len(usable) == 1:
        return _ready_resolution(usable[0], usable)
    if usable:
        return SpotifyDeviceResolution(
            status=SpotifyDeviceStatus.AMBIGUOUS,
            candidate_count=len(usable),
            detail="Choose which Spotify device Akiha should use.",
        )
    if devices:
        return SpotifyDeviceResolution(
            status=SpotifyDeviceStatus.RESTRICTED_ONLY,
            candidate_count=len(devices),
            detail="Spotify reported only restricted devices.",
        )
    return SpotifyDeviceResolution(
        status=SpotifyDeviceStatus.NO_DEVICE,
        detail="No Spotify playback device is currently available.",
    )


def _ready_resolution(
    device: SpotifyDevice,
    candidates: Sequence[SpotifyDevice],
) -> SpotifyDeviceResolution:
    return SpotifyDeviceResolution(
        status=SpotifyDeviceStatus.READY,
        selected_device=device,
        candidate_count=len(candidates),
        detail="A Spotify playback device is ready.",
    )


def _launch_failure_resolution(result: ActionResult) -> SpotifyDeviceResolution:
    if result.failure_category is ActionFailureCategory.PERMISSION_REQUIRED:
        status = SpotifyDeviceStatus.APP_PERMISSION_REQUIRED
        detail = "Launching Spotify needs the existing application permission."
    else:
        status = SpotifyDeviceStatus.APP_UNAVAILABLE
        detail = "Spotify could not be started through the approved action path."
    return SpotifyDeviceResolution(status=status, detail=detail)


def _cancelled_resolution() -> SpotifyDeviceResolution:
    return SpotifyDeviceResolution(
        status=SpotifyDeviceStatus.CANCELLED,
        detail="Spotify device selection was cancelled.",
    )


def _is_cancelled(token: ActionCancellationToken | None) -> bool:
    return token is not None and token.is_cancelled
