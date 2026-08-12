"""Persistent Qt/async bridge for one hosted live conversation."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from PySide6.QtCore import QThread, Signal

from project_akiha.app.hosted_live_session_controller import (
    HostedLiveSessionController,
)
from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.core.voice_session import (
    ActionProposal,
    AssistantTextRevision,
    AudioFrame,
    LiveSessionAdapter,
    LiveSessionCapabilities,
    LiveSessionConfig,
    LiveSessionError,
    LiveSessionStateEvent,
    SanitizedActionResult,
    SessionLifecycle,
    TranscriptRevision,
)
from project_akiha.services.provider_action_dispatcher import (
    ProviderActionConfirmation,
    ProviderActionDispatcher,
)
from project_akiha.services.provider_action_proposal_gateway import (
    ProviderActionProposalGateway,
)


class HostedLiveSessionThread(QThread):
    """Own Gemini's persistent asyncio loop outside the Qt UI thread."""

    connected = Signal()
    transcript_revised_signal = Signal(object)
    assistant_text_revised_signal = Signal(object)
    audio_received_signal = Signal(object)
    response_interrupted_signal = Signal(str)
    turn_completed_signal = Signal(str)
    failed_signal = Signal(str, str)
    session_state_changed_signal = Signal(object)
    capabilities_received_signal = Signal(object)
    action_result_signal = Signal(object)
    action_confirmation_requested_signal = Signal(object)

    def __init__(
        self,
        *,
        adapter_factory: Callable[[], LiveSessionAdapter],
        coordinator: VoiceSessionCoordinator,
        config_provider: Callable[[str], LiveSessionConfig],
        proposal_gateway: ProviderActionProposalGateway | None = None,
        action_dispatcher: ProviderActionDispatcher | None = None,
    ) -> None:
        super().__init__()
        self._adapter_factory = adapter_factory
        self._coordinator = coordinator
        self._config_provider = config_provider
        self._proposal_gateway = proposal_gateway
        self._action_dispatcher = action_dispatcher
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._controller: HostedLiveSessionController | None = None
        self._failure_emitted = False
        self._action_tasks: set[asyncio.Task[None]] = set()

    def run(self) -> None:
        """Run one live session until explicit stop or provider termination."""
        asyncio.run(self._run_session())

    def submit_audio(self, frame: AudioFrame) -> bool:
        """Queue one microphone frame on the owned asyncio loop."""
        return self._submit(lambda controller: controller.accept_audio(frame))

    def end_user_turn(self, turn_id: str) -> bool:
        """Queue a provider audio endpoint on the owned asyncio loop."""
        return self._submit(lambda controller: controller.end_user_turn(turn_id))

    def interrupt(self, turn_id: str) -> bool:
        """Queue provider-native interruption on the owned asyncio loop."""
        return self._submit(lambda controller: controller.interrupt(turn_id))

    def request_stop(self) -> None:
        """Request bounded asynchronous shutdown without blocking the caller."""
        self.requestInterruption()
        loop = self._loop
        stop_event = self._stop_event
        if loop is not None and stop_event is not None and loop.is_running():
            loop.call_soon_threadsafe(stop_event.set)

    def resolve_action_confirmation(
        self,
        confirmation: ProviderActionConfirmation,
        *,
        approved: bool,
    ) -> bool:
        """Queue one trusted local confirmation decision."""
        return self._submit(
            lambda controller: self._resolve_action_confirmation(
                controller,
                confirmation,
                approved=approved,
            )
        )

    def transcript_revised(self, revision: TranscriptRevision) -> None:
        self.transcript_revised_signal.emit(revision)

    def assistant_text_revised(self, revision: AssistantTextRevision) -> None:
        self.assistant_text_revised_signal.emit(revision)

    def audio_received(self, frame: AudioFrame) -> None:
        self.audio_received_signal.emit(frame)

    def action_proposed(self, proposal: ActionProposal) -> None:
        gateway = self._proposal_gateway
        dispatcher = self._action_dispatcher
        if gateway is None or dispatcher is None:
            self._emit_failure_once(
                "hosted_tool_gateway_unavailable",
                "Gemini Live action routing is unavailable.",
            )
            self.request_stop()
            return
        task = asyncio.create_task(
            self._dispatch_action_proposal(proposal),
            name=f"gemini-action-{proposal.proposal_id}",
        )
        self._action_tasks.add(task)
        task.add_done_callback(self._handle_action_task_done)

    def response_interrupted(self, turn_id: str) -> None:
        self.response_interrupted_signal.emit(turn_id)

    def turn_completed(self, turn_id: str) -> None:
        self.turn_completed_signal.emit(turn_id)

    def failed(self, code: str, message: str) -> None:
        self._emit_failure_once(code, message)
        self.request_stop()

    def session_state_changed(self, event: LiveSessionStateEvent) -> None:
        self.session_state_changed_signal.emit(event)
        if event.lifecycle in {SessionLifecycle.IDLE, SessionLifecycle.ERROR}:
            self.request_stop()

    def capabilities_received(self, capabilities: LiveSessionCapabilities) -> None:
        self.capabilities_received_signal.emit(capabilities)

    async def _run_session(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        controller = HostedLiveSessionController(
            adapter=self._adapter_factory(),
            coordinator=self._coordinator,
            event_sink=self,
            config_provider=self._config_provider,
        )
        self._controller = controller
        try:
            started = await controller.start()
            if not started:
                self._emit_failure_once(
                    "hosted_live_busy",
                    "Another voice session already owns the conversation runtime.",
                )
                return
            self.connected.emit()
            await self._stop_event.wait()
        except Exception:
            self._emit_failure_once(
                "hosted_live_start_failed",
                "Gemini Live could not start. Check Settings and the network.",
            )
        finally:
            action_tasks = tuple(self._action_tasks)
            self._action_tasks.clear()
            for task in action_tasks:
                task.cancel()
            if action_tasks:
                await asyncio.gather(*action_tasks, return_exceptions=True)
            if self._proposal_gateway is not None:
                self._proposal_gateway.clear()
            if self._action_dispatcher is not None:
                self._action_dispatcher.clear()
            try:
                await controller.close()
            except Exception:
                self._emit_failure_once(
                    "hosted_live_shutdown_failed",
                    "Gemini Live did not close cleanly.",
                )
            self._controller = None
            self._stop_event = None
            self._loop = None

    async def _dispatch_action_proposal(self, proposal: ActionProposal) -> None:
        gateway = self._proposal_gateway
        dispatcher = self._action_dispatcher
        controller = self._controller
        if gateway is None or dispatcher is None or controller is None:
            return
        conversion = gateway.convert(proposal)
        if conversion.decision.accepted:
            # Hosted audio currently has no parallel deterministic parser. The
            # provider proposal is released only after that local lane is known
            # to have produced no competing action for this turn.
            dispatcher.complete_local_routing(proposal.session_id, proposal.turn_id)
            result = await dispatcher.dispatch(conversion)
        else:
            result = SanitizedActionResult(
                session_id=proposal.session_id,
                turn_id=proposal.turn_id,
                proposal_id=proposal.proposal_id,
                status="denied",
                message="The action proposal was rejected safely.",
            )
        if result.status == "confirmation_required":
            confirmation = dispatcher.pending_confirmation(
                session_id=result.session_id,
                turn_id=result.turn_id,
                proposal_id=result.proposal_id,
            )
            if confirmation is not None:
                self.action_confirmation_requested_signal.emit(confirmation)
                return
        await self._return_action_result(controller, result)

    async def _resolve_action_confirmation(
        self,
        controller: HostedLiveSessionController,
        confirmation: ProviderActionConfirmation,
        *,
        approved: bool,
    ) -> None:
        dispatcher = self._action_dispatcher
        if dispatcher is None:
            return
        result = await dispatcher.resolve_confirmation(
            session_id=confirmation.session_id,
            turn_id=confirmation.turn_id,
            proposal_id=confirmation.proposal_id,
            approved=approved,
        )
        await self._return_action_result(controller, result)

    async def _return_action_result(
        self,
        controller: HostedLiveSessionController,
        result: SanitizedActionResult,
    ) -> None:
        await controller.accept_action_result(result)
        self.action_result_signal.emit(result)

    def _handle_action_task_done(self, task: asyncio.Task[None]) -> None:
        """Fail visibly when a detached provider-tool operation cannot finish."""
        self._action_tasks.discard(task)
        if task.cancelled():
            return
        try:
            task.result()
        except LiveSessionError as error:
            self._emit_failure_once(str(error.code), str(error))
            self.request_stop()
        except Exception:
            self._emit_failure_once(
                "hosted_tool_operation_failed",
                "Gemini Live stopped after an assistant action failed.",
            )
            self.request_stop()

    def _submit(
        self,
        operation: Callable[
            [HostedLiveSessionController],
            Coroutine[Any, Any, None],
        ],
    ) -> bool:
        loop = self._loop
        controller = self._controller
        if loop is None or controller is None or not loop.is_running():
            return False

        async def invoke() -> None:
            await operation(controller)

        future = asyncio.run_coroutine_threadsafe(invoke(), loop)

        def report_failure(completed) -> None:
            try:
                completed.result()
            except LiveSessionError as error:
                self._emit_failure_once(str(error.code), str(error))
                self.request_stop()
            except Exception:
                self._emit_failure_once(
                    "hosted_live_operation_failed",
                    "Gemini Live stopped after a provider operation failed.",
                )
                self.request_stop()

        future.add_done_callback(report_failure)
        return True

    def _emit_failure_once(self, code: str, message: str) -> None:
        if self._failure_emitted:
            return
        self._failure_emitted = True
        self.failed_signal.emit(code.strip() or "hosted_live_failed", message.strip())
