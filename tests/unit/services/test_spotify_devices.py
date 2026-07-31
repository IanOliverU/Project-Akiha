"""Tests for safe Spotify device selection and desktop activation."""

from __future__ import annotations

import asyncio
import unittest

from project_akiha.core.actions import (
    LAUNCH_APPLICATION_ACTION,
    ActionCancellationToken,
    ActionFailureCategory,
    ActionRequest,
    ActionResult,
    ActionStatus,
    PermissionDecision,
)
from project_akiha.services.spotify_auth import SpotifyOAuthError
from project_akiha.services.spotify_client import SpotifyAPIError, SpotifyDevice
from project_akiha.services.spotify_devices import (
    PermissionGatedSpotifyActivator,
    SpotifyDeviceCoordinator,
    SpotifyDeviceStatus,
    select_spotify_device,
)


class SpotifyDeviceSelectionTest(unittest.TestCase):
    def test_active_unrestricted_device_wins(self) -> None:
        inactive_computer = _device("pc", device_type="computer")
        active_phone = _device("phone", device_type="smartphone", is_active=True)

        result = select_spotify_device((inactive_computer, active_phone))

        self.assertEqual(result.status, SpotifyDeviceStatus.READY)
        self.assertEqual(result.selected_device, active_phone)

    def test_restricted_devices_are_never_selected(self) -> None:
        restricted = _device("restricted", is_active=True, is_restricted=True)
        computer = _device("pc", device_type="computer")

        result = select_spotify_device((restricted, computer))

        self.assertEqual(result.status, SpotifyDeviceStatus.READY)
        self.assertEqual(result.selected_device, computer)

    def test_only_restricted_devices_fail_closed(self) -> None:
        result = select_spotify_device((_device("locked", is_restricted=True),))

        self.assertEqual(result.status, SpotifyDeviceStatus.RESTRICTED_ONLY)
        self.assertIsNone(result.selected_device)

    def test_multiple_inactive_peers_require_selection(self) -> None:
        result = select_spotify_device(
            (
                _device("phone", device_type="smartphone"),
                _device("speaker", device_type="speaker"),
            )
        )

        self.assertEqual(result.status, SpotifyDeviceStatus.AMBIGUOUS)
        self.assertEqual(result.candidate_count, 2)


class SpotifyDeviceCoordinatorTest(unittest.TestCase):
    def test_disabled_auto_launch_returns_without_activation(self) -> None:
        source = _DeviceSource([()])
        activator = _Activator(_action_result(ActionStatus.SUCCESS))
        coordinator = SpotifyDeviceCoordinator(
            source,
            activator,
            auto_launch_desktop_app=False,
        )

        result = asyncio.run(coordinator.resolve("spotify-device-1"))

        self.assertEqual(result.status, SpotifyDeviceStatus.NO_DEVICE)
        self.assertEqual(activator.calls, [])

    def test_permission_denial_is_preserved_without_polling(self) -> None:
        source = _DeviceSource([()])
        activator = _Activator(
            _action_result(
                ActionStatus.DENIED,
                failure=ActionFailureCategory.PERMISSION_REQUIRED,
            )
        )
        coordinator = SpotifyDeviceCoordinator(source, activator)

        result = asyncio.run(coordinator.resolve("spotify-device-2"))

        self.assertEqual(result.status, SpotifyDeviceStatus.APP_PERMISSION_REQUIRED)
        self.assertEqual(source.call_count, 1)

    def test_restricted_only_snapshot_can_activate_desktop_app(self) -> None:
        desktop = _device("desktop", device_type="computer")
        source = _DeviceSource([(_device("locked", is_restricted=True),), (desktop,)])
        activator = _Activator(_action_result(ActionStatus.SUCCESS))
        coordinator = SpotifyDeviceCoordinator(
            source,
            activator,
            poll_attempts=1,
            poll_interval_seconds=0,
            sleeper=_no_sleep,
        )

        result = asyncio.run(coordinator.resolve("spotify-device-restricted"))

        self.assertEqual(result.status, SpotifyDeviceStatus.READY)
        self.assertEqual(result.selected_device, desktop)
        self.assertEqual(activator.calls, ["spotify-device-restricted"])

    def test_successful_activation_polls_until_desktop_appears(self) -> None:
        desktop = _device("desktop", device_type="computer")
        source = _DeviceSource([(), (), (desktop,)])
        activator = _Activator(_action_result(ActionStatus.SUCCESS))
        sleeps: list[float] = []

        async def sleeper(seconds: float) -> None:
            sleeps.append(seconds)

        coordinator = SpotifyDeviceCoordinator(
            source,
            activator,
            poll_attempts=3,
            poll_interval_seconds=0.25,
            sleeper=sleeper,
        )

        result = asyncio.run(coordinator.resolve("spotify-device-3"))

        self.assertEqual(result.status, SpotifyDeviceStatus.READY)
        self.assertEqual(result.selected_device, desktop)
        self.assertEqual(activator.calls, ["spotify-device-3"])
        self.assertEqual(sleeps, [0.25, 0.25])

    def test_polling_is_bounded_when_device_never_appears(self) -> None:
        source = _DeviceSource([(), (), ()])
        coordinator = SpotifyDeviceCoordinator(
            source,
            _Activator(_action_result(ActionStatus.SUCCESS)),
            poll_attempts=2,
            poll_interval_seconds=0,
            sleeper=_no_sleep,
        )

        result = asyncio.run(coordinator.resolve("spotify-device-4"))

        self.assertEqual(result.status, SpotifyDeviceStatus.APP_START_TIMEOUT)
        self.assertEqual(source.call_count, 3)

    def test_cancellation_prevents_device_and_activation_calls(self) -> None:
        token = ActionCancellationToken()
        token.cancel()
        source = _DeviceSource([()])
        activator = _Activator(_action_result(ActionStatus.SUCCESS))
        coordinator = SpotifyDeviceCoordinator(source, activator)

        result = asyncio.run(
            coordinator.resolve("spotify-device-5", cancellation_token=token)
        )

        self.assertEqual(result.status, SpotifyDeviceStatus.CANCELLED)
        self.assertEqual(source.call_count, 0)
        self.assertEqual(activator.calls, [])

    def test_provider_failure_is_sanitized_and_does_not_launch(self) -> None:
        source = _DeviceSource([SpotifyAPIError("private provider response")])
        activator = _Activator(_action_result(ActionStatus.SUCCESS))
        coordinator = SpotifyDeviceCoordinator(source, activator)

        result = asyncio.run(coordinator.resolve("spotify-device-6"))

        self.assertEqual(result.status, SpotifyDeviceStatus.FAILED)
        self.assertNotIn("private provider response", result.detail)
        self.assertEqual(activator.calls, [])

    def test_disconnected_session_returns_specific_safe_status(self) -> None:
        source = _DeviceSource([SpotifyOAuthError("private auth detail")])
        activator = _Activator(_action_result(ActionStatus.SUCCESS))
        coordinator = SpotifyDeviceCoordinator(source, activator)

        result = asyncio.run(coordinator.resolve("spotify-device-auth"))

        self.assertEqual(result.status, SpotifyDeviceStatus.NOT_CONNECTED)
        self.assertNotIn("private auth detail", result.detail)
        self.assertEqual(activator.calls, [])


class PermissionGatedSpotifyActivatorTest(unittest.TestCase):
    def test_activation_uses_only_the_registered_spotify_launch_action(self) -> None:
        service = _ActionService()
        activator = PermissionGatedSpotifyActivator(service)  # type: ignore[arg-type]

        result = asyncio.run(activator.activate("spotify-launch-1"))

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(len(service.requests), 1)
        request = service.requests[0]
        self.assertEqual(request.correlation_id, "spotify-launch-1")
        self.assertEqual(request.action_id, LAUNCH_APPLICATION_ACTION)
        self.assertEqual(request.source, "spotify")
        self.assertEqual(dict(request.parameters), {"application_id": "spotify"})


def _device(
    device_id: str,
    *,
    device_type: str = "speaker",
    is_active: bool = False,
    is_restricted: bool = False,
) -> SpotifyDevice:
    return SpotifyDevice(
        device_id=device_id,
        name=f"Device {device_id}",
        device_type=device_type,
        is_active=is_active,
        is_restricted=is_restricted,
    )


def _action_result(
    status: ActionStatus,
    *,
    failure: ActionFailureCategory | None = None,
) -> ActionResult:
    return ActionResult(
        correlation_id="spotify-test",
        action_id=LAUNCH_APPLICATION_ACTION,
        status=status,
        summary="Synthetic Spotify launch result.",
        permission_decision=(
            PermissionDecision.MISSING
            if failure is ActionFailureCategory.PERMISSION_REQUIRED
            else PermissionDecision.GRANTED
        ),
        failure_category=failure,
    )


class _DeviceSource:
    def __init__(
        self,
        responses: list[
            tuple[SpotifyDevice, ...] | SpotifyAPIError | SpotifyOAuthError
        ],
    ) -> None:
        self.responses = list(responses)
        self.call_count = 0

    def get_available_devices(self) -> tuple[SpotifyDevice, ...]:
        self.call_count += 1
        if not self.responses:
            raise AssertionError("Unexpected Spotify device request.")
        response = self.responses.pop(0)
        if isinstance(response, (SpotifyAPIError, SpotifyOAuthError)):
            raise response
        return response


class _Activator:
    def __init__(self, result: ActionResult) -> None:
        self.result = result
        self.calls: list[str] = []

    async def activate(
        self,
        correlation_id: str,
        *,
        cancellation_token: ActionCancellationToken | None = None,
    ) -> ActionResult:
        del cancellation_token
        self.calls.append(correlation_id)
        return self.result


class _ActionService:
    def __init__(self) -> None:
        self.requests: list[ActionRequest] = []

    async def evaluate_request(
        self,
        request: ActionRequest,
        *,
        confirmed: bool,
        cancellation_token: ActionCancellationToken | None,
    ) -> ActionResult:
        self.requests.append(request)
        self.assertions = (confirmed, cancellation_token)
        return _action_result(ActionStatus.SUCCESS)


async def _no_sleep(_seconds: float) -> None:
    return None


if __name__ == "__main__":
    unittest.main()
