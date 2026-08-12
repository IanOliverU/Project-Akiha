"""Tests for the persistent Qt/async hosted-live bridge."""

from __future__ import annotations

import time
import unittest

from PySide6.QtCore import QCoreApplication

from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.core.actions import (
    ActionResult,
    ActionStatus,
    PermissionDecision,
    build_default_provider_action_catalog,
)
from project_akiha.core.voice_session import (
    ActionProposal,
    AudioFrame,
    LiveResponseModality,
    LiveSessionConfig,
    LiveSessionError,
    LiveSessionErrorCode,
    LiveSessionStateEvent,
    SessionLifecycle,
    VoiceInputMode,
    VoiceProcessingMode,
)
from project_akiha.services.intent_arbitration import IntentArbiter
from project_akiha.services.provider_action_dispatcher import (
    ProviderActionDispatcher,
)
from project_akiha.services.provider_action_proposal_gateway import (
    ProviderActionProposalGateway,
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

    def test_operation_failure_preserves_privacy_safe_live_error(self) -> None:
        adapter = _FailingOperationAdapter()
        coordinator = VoiceSessionCoordinator(
            session_id_factory=lambda: "hosted-session-1"
        )
        worker = HostedLiveSessionThread(
            adapter_factory=lambda: adapter,
            coordinator=coordinator,
            config_provider=_config,
        )
        failures: list[tuple[str, str]] = []
        worker.failed_signal.connect(
            lambda code, message: failures.append((code, message))
        )

        worker.start()
        self.assertTrue(_wait_until(self.app, lambda: worker.submit_audio(_frame())))
        self.assertTrue(_wait_until(self.app, lambda: bool(failures)))
        self.assertTrue(worker.wait(2_000))

        self.assertEqual(
            failures,
            [("invalid_state", "The live turn is no longer active.")],
        )

    def test_tool_proposal_uses_gateway_dispatch_and_sanitized_result(self) -> None:
        adapter = _ToolAdapter()
        coordinator = VoiceSessionCoordinator(
            session_id_factory=lambda: "hosted-session-1"
        )
        gateway = ProviderActionProposalGateway(
            build_default_provider_action_catalog(),
            coordinator,
        )
        dispatcher = ProviderActionDispatcher(
            _SuccessfulActionService(),
            coordinator,
            IntentArbiter(),
        )
        worker = HostedLiveSessionThread(
            adapter_factory=lambda: adapter,
            coordinator=coordinator,
            config_provider=_config,
            proposal_gateway=gateway,
            action_dispatcher=dispatcher,
        )
        emitted_results: list[object] = []
        worker.action_result_signal.connect(emitted_results.append)

        worker.start()
        self.assertTrue(_wait_until(self.app, lambda: worker.isRunning()))
        self.assertTrue(
            _wait_until(
                self.app,
                lambda: coordinator.snapshot.lifecycle is SessionLifecycle.ACTIVE,
            )
        )
        turn = coordinator.begin_turn(VoiceInputMode.HOSTED_LIVE_CONVERSATION)
        frame = _frame(turn_id=turn.turn_id)
        self.assertTrue(worker.submit_audio(frame))
        self.assertTrue(_wait_until(self.app, lambda: bool(adapter.action_results)))

        result = adapter.action_results[0]
        self.assertEqual(result.status, "success")
        self.assertEqual(result.message, "The approved action completed.")
        self.assertTrue(_wait_until(self.app, lambda: bool(emitted_results)))

        worker.request_stop()
        self.assertTrue(worker.wait(2_000))

    def test_confirmation_waits_for_trusted_local_decision(self) -> None:
        adapter = _ConfirmationToolAdapter()
        coordinator = VoiceSessionCoordinator(
            session_id_factory=lambda: "hosted-session-1"
        )
        gateway = ProviderActionProposalGateway(
            build_default_provider_action_catalog(),
            coordinator,
        )
        dispatcher = ProviderActionDispatcher(
            _ConfirmationActionService(),
            coordinator,
            IntentArbiter(),
        )
        worker = HostedLiveSessionThread(
            adapter_factory=lambda: adapter,
            coordinator=coordinator,
            config_provider=_config,
            proposal_gateway=gateway,
            action_dispatcher=dispatcher,
        )
        confirmations = []

        def approve(confirmation) -> None:
            confirmations.append(confirmation)
            self.assertTrue(
                worker.resolve_action_confirmation(confirmation, approved=True)
            )

        worker.action_confirmation_requested_signal.connect(approve)
        worker.start()
        self.assertTrue(
            _wait_until(
                self.app,
                lambda: coordinator.snapshot.lifecycle is SessionLifecycle.ACTIVE,
            )
        )
        turn = coordinator.begin_turn(VoiceInputMode.HOSTED_LIVE_CONVERSATION)
        self.assertTrue(worker.submit_audio(_frame(turn_id=turn.turn_id)))
        self.assertTrue(_wait_until(self.app, lambda: bool(adapter.action_results)))

        self.assertEqual(len(confirmations), 1)
        self.assertIn("notes.txt", confirmations[0].prompt)
        self.assertEqual(adapter.action_results[0].status, "success")

        worker.request_stop()
        self.assertTrue(worker.wait(2_000))

    def test_tool_task_failure_stops_visibly_instead_of_stranding_turn(self) -> None:
        adapter = _FailingToolResultAdapter()
        coordinator = VoiceSessionCoordinator(
            session_id_factory=lambda: "hosted-session-1"
        )
        worker = HostedLiveSessionThread(
            adapter_factory=lambda: adapter,
            coordinator=coordinator,
            config_provider=_config,
            proposal_gateway=ProviderActionProposalGateway(
                build_default_provider_action_catalog(),
                coordinator,
            ),
            action_dispatcher=ProviderActionDispatcher(
                _SuccessfulActionService(),
                coordinator,
                IntentArbiter(),
            ),
        )
        failures: list[tuple[str, str]] = []
        worker.failed_signal.connect(
            lambda code, message: failures.append((code, message))
        )

        worker.start()
        self.assertTrue(
            _wait_until(
                self.app,
                lambda: coordinator.snapshot.lifecycle is SessionLifecycle.ACTIVE,
            )
        )
        turn = coordinator.begin_turn(VoiceInputMode.HOSTED_LIVE_CONVERSATION)
        self.assertTrue(worker.submit_audio(_frame(turn_id=turn.turn_id)))

        self.assertTrue(_wait_until(self.app, lambda: bool(failures)))
        self.assertTrue(worker.wait(2_000))
        self.assertEqual(
            failures,
            [
                (
                    "hosted_tool_operation_failed",
                    "Gemini Live stopped after an assistant action failed.",
                )
            ],
        )


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


class _FailingOperationAdapter(_Adapter):
    async def accept_audio(self, frame) -> None:
        del frame
        raise LiveSessionError(
            LiveSessionErrorCode.INVALID_STATE,
            "The live turn is no longer active.",
        )


class _ToolAdapter(_Adapter):
    def __init__(self) -> None:
        super().__init__()
        self.action_results = []

    async def accept_audio(self, frame) -> None:
        assert self.sink is not None
        self.sink.action_proposed(
            ActionProposal(
                session_id=frame.session_id,
                turn_id=frame.turn_id,
                proposal_id="gemini-tool-1",
                source="gemini-live",
                action_name="spotify.pause",
                arguments={"service": "spotify"},
            )
        )

    async def accept_action_result(self, result) -> None:
        self.action_results.append(result)


class _ConfirmationToolAdapter(_ToolAdapter):
    async def accept_audio(self, frame) -> None:
        assert self.sink is not None
        self.sink.action_proposed(
            ActionProposal(
                session_id=frame.session_id,
                turn_id=frame.turn_id,
                proposal_id="gemini-tool-confirm-1",
                source="gemini-live",
                action_name="files.open",
                arguments={"path": r"C:\Users\Private\notes.txt"},
            )
        )


class _FailingToolResultAdapter(_ToolAdapter):
    async def accept_action_result(self, result) -> None:
        del result
        raise RuntimeError("private provider result failure")


class _SuccessfulActionService:
    async def evaluate_request(
        self,
        request,
        *,
        confirmed=False,
        cancellation_token=None,
    ) -> ActionResult:
        del confirmed, cancellation_token
        return ActionResult(
            correlation_id=request.correlation_id,
            action_id=request.action_id,
            status=ActionStatus.SUCCESS,
            summary="Private local result.",
            permission_decision=PermissionDecision.GRANTED,
        )


class _ConfirmationActionService:
    async def evaluate_request(
        self,
        request,
        *,
        confirmed=False,
        cancellation_token=None,
    ) -> ActionResult:
        del cancellation_token
        return ActionResult(
            correlation_id=request.correlation_id,
            action_id=request.action_id,
            status=(
                ActionStatus.SUCCESS
                if confirmed
                else ActionStatus.CONFIRMATION_REQUIRED
            ),
            summary="Private local result.",
            permission_decision=(
                PermissionDecision.GRANTED
                if confirmed
                else PermissionDecision.CONFIRMATION_REQUIRED
            ),
        )


def _config(session_id: str) -> LiveSessionConfig:
    return LiveSessionConfig(
        session_id=session_id,
        processing_mode=VoiceProcessingMode.HOSTED_LIVE,
        provider_name="gemini",
        input_sample_rate_hz=16_000,
        max_duration_seconds=600,
        response_modality=LiveResponseModality.AUDIO,
    )


def _frame(*, turn_id: str = "turn-1") -> AudioFrame:
    return AudioFrame(
        session_id="hosted-session-1",
        turn_id=turn_id,
        sequence_number=0,
        captured_at_monotonic=1.0,
        sample_rate_hz=16_000,
        channels=1,
        sample_width_bytes=2,
        data=b"\x00\x00" * 320,
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
