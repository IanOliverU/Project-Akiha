"""Own explicit Start/End lifecycle for one hosted live conversation."""

from __future__ import annotations

from collections.abc import Callable

from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.core.voice_session import (
    ActionProposal,
    AssistantTextRevision,
    AudioFrame,
    LiveSessionAdapter,
    LiveSessionCapabilities,
    LiveSessionConfig,
    LiveSessionEventSink,
    LiveSessionStateEvent,
    SanitizedActionResult,
    SessionLifecycle,
    TranscriptRevision,
    VoiceCancellationToken,
    VoiceProcessingMode,
)


class HostedLiveSessionController:
    """Synchronize one hosted adapter with Akiha's canonical coordinator."""

    def __init__(
        self,
        *,
        adapter: LiveSessionAdapter,
        coordinator: VoiceSessionCoordinator,
        event_sink: LiveSessionEventSink,
        config_provider: Callable[[str], LiveSessionConfig],
    ) -> None:
        self._adapter = adapter
        self._coordinator = coordinator
        self._event_sink = event_sink
        self._config_provider = config_provider
        self._cancellation_token: VoiceCancellationToken | None = None
        self._active = False
        self._operation_active = False

    @property
    def active(self) -> bool:
        """Return whether the user owns a hosted conversation session."""
        return self._active

    async def start(self) -> bool:
        """Reserve one logical session and connect its selected live adapter."""
        if self._operation_active or self._active:
            return False
        if self._coordinator.snapshot.lifecycle is not SessionLifecycle.IDLE:
            return False

        self._operation_active = True
        token = VoiceCancellationToken()
        self._cancellation_token = token
        try:
            starting = self._coordinator.request_start(VoiceProcessingMode.HOSTED_LIVE)
            session_id = starting.session_id
            assert session_id is not None
            config = self._config_provider(session_id)
            if config.session_id != session_id:
                raise ValueError(
                    "Hosted live configuration must use the reserved session ID."
                )
            await self._adapter.start(config, self, token)
            if self._coordinator.snapshot.lifecycle is SessionLifecycle.STARTING:
                self._coordinator.activate()
            self._active = True
            return True
        except Exception:
            token.cancel()
            await self._adapter.stop()
            self._coordinator.close()
            self._cancellation_token = None
            self._active = False
            raise
        finally:
            self._operation_active = False

    async def end(self) -> bool:
        """Cancel provider work and release the logical session exactly once."""
        if self._operation_active:
            return False
        if (
            not self._active
            and self._coordinator.snapshot.lifecycle is SessionLifecycle.IDLE
        ):
            return False

        self._operation_active = True
        self._active = False
        token = self._cancellation_token
        self._cancellation_token = None
        if token is not None:
            token.cancel()
        try:
            self._coordinator.request_stop()
            await self._adapter.stop()
            self._coordinator.finish_stop()
            return True
        finally:
            self._operation_active = False

    async def close(self) -> None:
        """Release hosted provider ownership during application shutdown."""
        await self.end()

    async def accept_audio(self, frame: AudioFrame) -> None:
        """Forward one owned microphone frame to the active adapter."""
        if not self._active:
            raise RuntimeError("Hosted live audio requires an active session.")
        await self._adapter.accept_audio(frame)

    async def end_user_turn(self, turn_id: str) -> None:
        """End one provider audio turn without closing the conversation."""
        if not self._active:
            raise RuntimeError("Hosted live input requires an active session.")
        await self._adapter.end_user_turn(turn_id)

    async def interrupt(self, turn_id: str) -> None:
        """Request provider-native interruption for the currently owned turn."""
        if not self._active:
            raise RuntimeError("Hosted live interruption requires an active session.")
        await self._adapter.interrupt(turn_id)

    async def accept_action_result(self, result: SanitizedActionResult) -> None:
        """Return one application-sanitized result to the active adapter."""
        if not self._active:
            raise RuntimeError("Hosted live tools require an active session.")
        await self._adapter.accept_action_result(result)

    def transcript_revised(self, revision: TranscriptRevision) -> None:
        self._event_sink.transcript_revised(revision)

    def assistant_text_revised(self, revision: AssistantTextRevision) -> None:
        self._event_sink.assistant_text_revised(revision)

    def audio_received(self, frame: AudioFrame) -> None:
        self._event_sink.audio_received(frame)

    def action_proposed(self, proposal: ActionProposal) -> None:
        self._event_sink.action_proposed(proposal)

    def response_interrupted(self, turn_id: str) -> None:
        self._event_sink.response_interrupted(turn_id)

    def turn_completed(self, turn_id: str) -> None:
        self._event_sink.turn_completed(turn_id)

    def failed(self, code: str, message: str) -> None:
        lifecycle = self._coordinator.snapshot.lifecycle
        if lifecycle in {SessionLifecycle.STARTING, SessionLifecycle.ACTIVE}:
            self._coordinator.report_error(code)
        self._active = False
        self._event_sink.failed(code, message)

    def session_state_changed(self, event: LiveSessionStateEvent) -> None:
        lifecycle = self._coordinator.snapshot.lifecycle
        if event.lifecycle is SessionLifecycle.ACTIVE:
            if lifecycle is SessionLifecycle.STARTING:
                self._coordinator.activate()
            self._active = True
        elif event.lifecycle is SessionLifecycle.STOPPING:
            self._active = False
            self._coordinator.request_stop()
        elif event.lifecycle is SessionLifecycle.IDLE:
            self._active = False
            if lifecycle is not SessionLifecycle.IDLE:
                self._coordinator.request_stop()
                self._coordinator.finish_stop()
            self._cancellation_token = None
        self._event_sink.session_state_changed(event)

    def capabilities_received(self, capabilities: LiveSessionCapabilities) -> None:
        self._event_sink.capabilities_received(capabilities)
