"""Provider-neutral protocols for modular and hosted-live voice lanes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from project_akiha.core.voice_session.models import (
    ActionProposal,
    AssistantTextRevision,
    AudioFrame,
    EndpointReason,
    LiveSessionCapabilities,
    LiveSessionConfig,
    LiveSessionStateEvent,
    SanitizedActionResult,
    TranscriptRevision,
    VoiceCancellationToken,
)

TranscriptCallback = Callable[[TranscriptRevision], None]


class LiveSessionEventSink(Protocol):
    """Receive canonical events without exposing provider-specific classes."""

    def transcript_revised(self, revision: TranscriptRevision) -> None:
        """Receive replaceable or final user transcription."""

    def assistant_text_revised(self, revision: AssistantTextRevision) -> None:
        """Receive ordered assistant response text."""

    def audio_received(self, frame: AudioFrame) -> None:
        """Receive ordered native response audio."""

    def action_proposed(self, proposal: ActionProposal) -> None:
        """Receive an untrusted typed action proposal."""

    def response_interrupted(self, turn_id: str) -> None:
        """Receive provider confirmation that one response was interrupted."""

    def turn_completed(self, turn_id: str) -> None:
        """Receive provider confirmation that one model turn completed."""

    def failed(self, code: str, message: str) -> None:
        """Receive a sanitized provider failure."""

    def session_state_changed(self, event: LiveSessionStateEvent) -> None:
        """Receive a privacy-safe lifecycle update."""

    def capabilities_received(self, capabilities: LiveSessionCapabilities) -> None:
        """Receive the adapter's explicit feature set."""


class LiveSessionAdapter(Protocol):
    """Persistent provider session isolated from UI and action executors."""

    async def start(
        self,
        config: LiveSessionConfig,
        event_sink: LiveSessionEventSink,
        cancellation_token: VoiceCancellationToken,
    ) -> None:
        """Start the selected provider session with explicit ownership."""

    async def accept_audio(self, frame: AudioFrame) -> None:
        """Accept one bounded microphone frame."""

    async def end_user_turn(self, turn_id: str) -> None:
        """Signal the end of one user turn when the provider requires it."""

    async def accept_action_result(self, result: SanitizedActionResult) -> None:
        """Return one sanitized typed-action result."""

    async def interrupt(self, turn_id: str) -> None:
        """Interrupt response work owned by one turn."""

    async def stop(self) -> None:
        """Stop the session and release provider resources."""


class StreamingSpeechRecognizer(Protocol):
    """Incremental local recognition without microphone ownership."""

    def start_turn(
        self,
        session_id: str,
        turn_id: str,
        on_revision: TranscriptCallback,
        cancellation_token: VoiceCancellationToken,
    ) -> None:
        """Start one recognition turn."""

    async def accept_audio(self, frame: AudioFrame) -> None:
        """Accept one ordered audio frame."""

    async def finalize(self, endpoint_reason: EndpointReason) -> None:
        """Finalize the bounded utterance buffer."""

    def cancel(self) -> None:
        """Cancel recognition and discard late results."""
