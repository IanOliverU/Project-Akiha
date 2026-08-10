"""Compose hosted-live transport with Akiha's existing voice owners."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from time import monotonic

from project_akiha.app.chat_controller import CanonicalLiveChatCommit
from project_akiha.app.live_audio_playback import NativeAudioPlaybackQueue
from project_akiha.app.live_transcript_controller import LiveTranscriptController
from project_akiha.app.voice_audio_bridge import RealtimeAudioFrameBridge
from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.core.events.bus import EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.core.voice_session import (
    AssistantTextRevision,
    AudioFrame,
    LiveSessionStateEvent,
    SessionLifecycle,
    TranscriptRevision,
    VoiceInputMode,
)
from project_akiha.providers.voice import CapturedAudio
from project_akiha.ui.hosted_live_session_worker import HostedLiveSessionThread


class HostedConversationRuntime:
    """Own one explicit cloud-audio session without local fallback."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        voice_controller: VoiceController,
        coordinator: VoiceSessionCoordinator,
        transcripts: LiveTranscriptController,
        audio_bridge: RealtimeAudioFrameBridge,
        playback: NativeAudioPlaybackQueue,
        thread_factory: Callable[[], HostedLiveSessionThread],
        on_commit: Callable[[CanonicalLiveChatCommit], None],
        on_stopped: Callable[[], None] | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        self._event_bus = event_bus
        self._voice_controller = voice_controller
        self._coordinator = coordinator
        self._transcripts = transcripts
        self._audio_bridge = audio_bridge
        self._playback = playback
        self._thread_factory = thread_factory
        self._on_commit = on_commit
        self._on_stopped = on_stopped
        self._monotonic_clock = monotonic_clock
        self._thread: HostedLiveSessionThread | None = None
        self._active = False
        self._started_at: float | None = None
        self._turn_id: str | None = None
        self._native_output_started = False

    @property
    def active(self) -> bool:
        """Return whether the user explicitly owns a hosted conversation."""
        return self._active

    def set_stopped_callback(self, callback: Callable[[], None] | None) -> None:
        """Observe asynchronous provider termination without selecting fallback."""
        self._on_stopped = callback

    def start(self) -> bool:
        """Start only Gemini Live after the user selects and requests it."""
        config = self._voice_controller.config
        if self._active:
            return False
        if not config.enabled or not config.push_to_talk_enabled:
            self._voice_controller.notify_error(
                "hosted_live_input_unavailable",
                "Gemini Live requires enabled voice and microphone controls.",
            )
            return False
        if (
            self._voice_controller.state is not VoiceState.IDLE
            or self._voice_controller.operation != "none"
            or self._coordinator.snapshot.lifecycle is not SessionLifecycle.IDLE
        ):
            self._voice_controller.notify_error(
                "hosted_live_busy",
                "Finish the current voice operation before starting Gemini Live.",
            )
            return False
        try:
            thread = self._thread_factory()
        except Exception as error:
            self._voice_controller.notify_error(
                "hosted_live_unavailable",
                str(error).strip() or "Gemini Live is unavailable.",
            )
            return False

        self._connect_thread(thread)
        self._thread = thread
        self._active = True
        self._started_at = self._monotonic_clock()
        self._publish_state(active=True, reason="connecting")
        thread.start()
        return True

    def end(self, reason: str = "user") -> bool:
        """Stop hosted capture and playback without starting Local Modular."""
        if not self._active:
            return False
        self._release_turn(cancel=True)
        thread = self._thread
        if thread is not None:
            thread.request_stop()
        self._set_inactive(reason)
        return True

    def tick(self) -> None:
        """Refresh the visible cloud-session elapsed timer."""
        if self._active:
            self._publish_state(active=True)

    def submit_audio(self, audio: CapturedAudio) -> None:
        """Send one direct PCM frame only to the active hosted worker."""
        thread = self._thread
        if not self._active or thread is None or not self._audio_bridge.is_active:
            return
        try:
            frame = self._audio_bridge.accept(audio)
        except (RuntimeError, ValueError):
            self._fail_visible(
                "hosted_audio_invalid",
                "Gemini Live microphone audio became invalid.",
            )
            return
        if not thread.submit_audio(frame):
            self._fail_visible(
                "hosted_audio_unavailable",
                "Gemini Live stopped accepting microphone audio.",
            )

    def end_user_turn(self) -> None:
        """Close the current microphone stream at Akiha's local endpoint."""
        thread = self._thread
        turn_id = self._turn_id
        self._audio_bridge.release()
        if not self._active or thread is None or turn_id is None:
            return
        if not thread.end_user_turn(turn_id):
            self._fail_visible(
                "hosted_endpoint_failed",
                "Gemini Live could not finish the microphone turn.",
            )

    def fail_input(self, code: str, message: str) -> None:
        """End the cloud session visibly after microphone failure."""
        self._fail_visible(code, message)

    def request_talk(self) -> bool:
        """Interrupt hosted output locally and open a replacement microphone turn."""
        if not self._active:
            return False
        thread = self._thread
        interrupted_turn_id = self._turn_id
        if thread is None or interrupted_turn_id is None:
            return False
        if self._voice_controller.state not in {
            VoiceState.THINKING,
            VoiceState.SPEAKING,
        }:
            return False

        self._event_bus.publish(
            EventType.VOICE_SPEAK_STOP_REQUESTED,
            {"reason": "hosted_live_interrupted"},
        )
        self._playback.cancel()
        self._audio_bridge.release()
        self._transcripts.cancel_turn(interrupted_turn_id)
        replacement = self._coordinator.replace_turn(
            VoiceInputMode.HOSTED_LIVE_CONVERSATION
        )
        self._turn_id = replacement.turn_id
        self._native_output_started = False
        self._transcripts.start_turn(
            session_id=replacement.session_id,
            turn_id=replacement.turn_id,
        )
        self._audio_bridge.start_turn(
            session_id=replacement.session_id,
            turn_id=replacement.turn_id,
        )
        self._playback.start_turn(
            session_id=replacement.session_id,
            turn_id=replacement.turn_id,
            on_complete=self._handle_playback_completed,
            on_error=self._fail_visible,
        )
        self._voice_controller.recover()
        if not thread.interrupt(interrupted_turn_id):
            self._fail_visible(
                "hosted_interruption_failed",
                "Gemini Live could not interrupt the previous response.",
            )
            return False
        self._event_bus.publish(
            EventType.VOICE_LISTEN_REQUESTED,
            {"source": "hosted_live"},
        )
        return True

    def close(self) -> None:
        """Request shutdown and wait briefly for the provider thread."""
        if self._active:
            self.end("shutdown")
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.request_stop()
            thread.wait(3_000)

    def _connect_thread(self, thread: HostedLiveSessionThread) -> None:
        thread.connected.connect(self._handle_connected)
        thread.transcript_revised_signal.connect(self._handle_transcript)
        thread.assistant_text_revised_signal.connect(self._handle_assistant_text)
        thread.audio_received_signal.connect(self._handle_audio)
        thread.response_interrupted_signal.connect(self._handle_interrupted)
        thread.turn_completed_signal.connect(self._handle_turn_completed)
        thread.failed_signal.connect(self._fail_visible)
        thread.session_state_changed_signal.connect(self._handle_session_state)
        thread.finished.connect(self._handle_thread_finished)

    def _handle_connected(self) -> None:
        if not self._active:
            thread = self._thread
            if thread is not None:
                thread.request_stop()
            return
        self._begin_turn()
        self._publish_state(active=True, reason="connected")

    def _begin_turn(self) -> None:
        turn = self._coordinator.begin_turn(VoiceInputMode.HOSTED_LIVE_CONVERSATION)
        self._turn_id = turn.turn_id
        self._native_output_started = False
        self._transcripts.start_turn(
            session_id=turn.session_id,
            turn_id=turn.turn_id,
        )
        self._audio_bridge.start_turn(
            session_id=turn.session_id,
            turn_id=turn.turn_id,
        )
        self._playback.start_turn(
            session_id=turn.session_id,
            turn_id=turn.turn_id,
            on_complete=self._handle_playback_completed,
            on_error=self._fail_visible,
        )
        self._event_bus.publish(
            EventType.VOICE_LISTEN_REQUESTED,
            {"source": "hosted_live"},
        )

    def _handle_transcript(self, revision: TranscriptRevision) -> None:
        self._transcripts.transcript_revised(revision)

    def _handle_assistant_text(self, revision: AssistantTextRevision) -> None:
        self._transcripts.assistant_text_revised(revision)

    def _handle_audio(self, frame: AudioFrame) -> None:
        if not self._owns_turn(frame.turn_id):
            return
        if not self._native_output_started:
            if not self._voice_controller.begin_hosted_output():
                self._fail_visible(
                    "hosted_playback_busy",
                    "Gemini Live audio could not claim playback.",
                )
                return
            self._native_output_started = True
        try:
            self._playback.submit(frame)
        except Exception:
            self._fail_visible(
                "hosted_playback_failed",
                "Gemini Live audio playback failed.",
            )

    def _handle_interrupted(self, turn_id: str) -> None:
        if self._owns_turn(turn_id):
            self._release_turn(cancel=True)

    def _handle_turn_completed(self, turn_id: str) -> None:
        if not self._owns_turn(turn_id):
            return
        self._transcripts.turn_completed(turn_id)
        try:
            commit = asyncio.run(
                self._transcripts.commit_completed_turn(
                    turn_id,
                    allow_audio_only=True,
                )
            )
        except Exception:
            self._fail_visible(
                "hosted_transcript_commit_failed",
                "Gemini Live transcript persistence failed.",
            )
            return
        if commit is not None:
            self._on_commit(commit)
        else:
            # Never let a missing provider transcript strand the next live
            # turn. Partials remain ephemeral when no canonical final exists.
            self._transcripts.cancel_turn(turn_id)
        self._playback.finish_turn()

    def _handle_playback_completed(self) -> None:
        if not self._active:
            return
        turn_id = self._turn_id
        snapshot = self._coordinator.snapshot
        session_id = snapshot.session_id
        if turn_id is not None and session_id is not None:
            self._coordinator.complete_turn(session_id, turn_id)
        self._turn_id = None
        self._native_output_started = False
        self._voice_controller.recover()
        self._begin_turn()

    def _handle_session_state(self, event: LiveSessionStateEvent) -> None:
        if event.lifecycle is SessionLifecycle.IDLE and self._active:
            self._release_turn(cancel=True)
            self._set_inactive(event.reason or "provider_closed")

    def _handle_thread_finished(self) -> None:
        if self._active:
            self._release_turn(cancel=True)
            self._set_inactive("provider_closed")
        self._thread = None

    def _fail_visible(self, code: str, message: str) -> None:
        if not self._active:
            return
        self._voice_controller.notify_error(code, message)
        self._release_turn(cancel=True)
        thread = self._thread
        if thread is not None:
            thread.request_stop()
        self._set_inactive("provider_error")

    def _release_turn(self, *, cancel: bool) -> None:
        turn_id = self._turn_id
        if self._voice_controller.operation == "input":
            self._event_bus.publish(
                EventType.VOICE_LISTEN_CANCEL_REQUESTED,
                {"reason": "hosted_live_stopped"},
            )
        elif self._voice_controller.operation == "output":
            self._event_bus.publish(
                EventType.VOICE_SPEAK_STOP_REQUESTED,
                {"reason": "hosted_live_stopped"},
            )
        self._playback.cancel()
        self._audio_bridge.release()
        if cancel and turn_id is not None:
            self._transcripts.cancel_turn(turn_id)
            self._coordinator.cancel_active_turn()
        self._turn_id = None
        self._native_output_started = False
        self._voice_controller.recover()

    def _owns_turn(self, turn_id: str) -> bool:
        snapshot = self._coordinator.snapshot
        session_id = snapshot.session_id
        return (
            self._active
            and turn_id == self._turn_id
            and session_id is not None
            and self._coordinator.accepts_callback(session_id, turn_id)
        )

    def _set_inactive(self, reason: str) -> None:
        if not self._active:
            return
        self._active = False
        self._publish_state(active=False, reason=reason)
        self._started_at = None
        callback = self._on_stopped
        if callback is not None:
            callback()

    def _publish_state(self, *, active: bool, reason: str = "") -> None:
        started_at = self._started_at
        elapsed = (
            max(0, int(self._monotonic_clock() - started_at))
            if active and started_at is not None
            else 0
        )
        self._event_bus.publish(
            EventType.VOICE_CONVERSATION_STATE_CHANGED,
            {
                "active": active,
                "mode": "cloud",
                "elapsed_seconds": elapsed,
                "reason": reason,
            },
        )
