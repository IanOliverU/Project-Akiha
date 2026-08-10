"""Tests for the persistent Qt/async hosted-live bridge."""

from __future__ import annotations

import time
import unittest

from PySide6.QtCore import QCoreApplication

from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.core.voice_session import (
    LiveResponseModality,
    LiveSessionConfig,
    LiveSessionStateEvent,
    SessionLifecycle,
    VoiceProcessingMode,
)
from project_akiha.ui.hosted_live_session_worker import HostedLiveSessionThread


class HostedLiveSessionThreadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_worker_keeps_session_alive_until_explicit_stop(self) -> None:
        adapter = _Adapter()
        coordinator = VoiceSessionCoordinator(
            session_id_factory=lambda: "hosted-session-1"
        )
        worker = HostedLiveSessionThread(
            adapter_factory=lambda: adapter,
            coordinator=coordinator,
            config_provider=_config,
        )
        connected: list[bool] = []
        worker.connected.connect(lambda: connected.append(True))

        worker.start()
        self.assertTrue(_wait_until(self.app, lambda: connected == [True]))
        self.assertTrue(worker.isRunning())
        self.assertEqual(coordinator.snapshot.lifecycle, SessionLifecycle.ACTIVE)

        worker.request_stop()
        self.assertTrue(worker.wait(2_000))
        self.app.processEvents()

        self.assertEqual(adapter.stop_count, 1)
        self.assertEqual(coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)

    def test_start_failure_is_visible_and_does_not_leave_session_owned(self) -> None:
        coordinator = VoiceSessionCoordinator(
            session_id_factory=lambda: "hosted-session-1"
        )
        worker = HostedLiveSessionThread(
            adapter_factory=_FailingAdapter,
            coordinator=coordinator,
            config_provider=_config,
        )
        failures: list[tuple[str, str]] = []
        worker.failed_signal.connect(
            lambda code, message: failures.append((code, message))
        )

        worker.start()
        self.assertTrue(worker.wait(2_000))
        self.assertTrue(_wait_until(self.app, lambda: bool(failures)))

        self.assertEqual(failures[0][0], "hosted_live_start_failed")
        self.assertEqual(coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)


class _Adapter:
    def __init__(self) -> None:
        self.sink = None
        self.config: LiveSessionConfig | None = None
        self.stop_count = 0

    async def start(self, config, event_sink, cancellation_token) -> None:
        del cancellation_token
        self.config = config
        self.sink = event_sink
        event_sink.session_state_changed(
            LiveSessionStateEvent(
                session_id=config.session_id,
                provider_name="gemini",
                lifecycle=SessionLifecycle.ACTIVE,
            )
        )

    async def stop(self) -> None:
        self.stop_count += 1
        if self.sink is None or self.config is None:
            return
        for lifecycle in (SessionLifecycle.STOPPING, SessionLifecycle.IDLE):
            self.sink.session_state_changed(
                LiveSessionStateEvent(
                    session_id=self.config.session_id,
                    provider_name="gemini",
                    lifecycle=lifecycle,
                    reason="stopped",
                )
            )

    async def accept_audio(self, frame) -> None:
        del frame

    async def end_user_turn(self, turn_id: str) -> None:
        del turn_id

    async def accept_action_result(self, result) -> None:
        del result

    async def interrupt(self, turn_id: str) -> None:
        del turn_id


class _FailingAdapter(_Adapter):
    async def start(self, config, event_sink, cancellation_token) -> None:
        del config, event_sink, cancellation_token
        raise RuntimeError("private provider failure")


def _config(session_id: str) -> LiveSessionConfig:
    return LiveSessionConfig(
        session_id=session_id,
        processing_mode=VoiceProcessingMode.HOSTED_LIVE,
        provider_name="gemini",
        input_sample_rate_hz=16_000,
        max_duration_seconds=600,
        response_modality=LiveResponseModality.AUDIO,
    )


def _wait_until(
    app: QCoreApplication,
    predicate,
    *,
    timeout_seconds: float = 2.0,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(predicate())


if __name__ == "__main__":
    unittest.main()
