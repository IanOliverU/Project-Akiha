"""Provider-neutral contracts for concurrent voice sessions and turns."""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_MAX_AUDIO_FRAME_BYTES = 1_048_576
_MAX_TEXT_CHARS = 65_536
_MAX_ACTION_ARGUMENTS = 32
_MAX_ACTION_ARGUMENT_TEXT_CHARS = 4_096


class VoiceProcessingMode(StrEnum):
    """Explicit privacy and provider lane selected for one voice turn."""

    LOCAL_MODULAR = "local_modular"
    HYBRID_API_MODULAR = "hybrid_api_modular"
    HOSTED_LIVE = "hosted_live"


class VoiceInputMode(StrEnum):
    """User-visible interaction mode that owns a voice turn."""

    PUSH_TO_TALK = "push_to_talk"
    LOCAL_CONVERSATION = "local_conversation"
    HOSTED_LIVE_CONVERSATION = "hosted_live_conversation"


class TranscriptStatus(StrEnum):
    """Whether recognized text remains replaceable or is authoritative."""

    PARTIAL = "partial"
    FINAL = "final"


class TranscriptConfidence(StrEnum):
    """Privacy-safe confidence band exposed by a recognizer."""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EndpointReason(StrEnum):
    """Bounded reason that recognition accepted a final transcript."""

    MANUAL_STOP = "manual_stop"
    SILENCE = "silence"
    TIME_LIMIT = "time_limit"
    PROVIDER_FINAL = "provider_final"


class SessionLifecycle(StrEnum):
    """Resource-ownership state for a voice session."""

    IDLE = "idle"
    STARTING = "starting"
    ACTIVE = "active"
    STOPPING = "stopping"
    ERROR = "error"


class VoiceStage(StrEnum):
    """Named concurrent stage that may advance independently."""

    CAPTURE = "capture"
    RECOGNITION = "recognition"
    INTENT = "intent"
    GENERATION = "generation"
    SYNTHESIS = "synthesis"
    PLAYBACK = "playback"


class VoiceSessionCue(StrEnum):
    """Dominant user-visible cue derived from concurrent stage state."""

    IDLE = "idle"
    LISTENING = "listening"
    CONFIRMING = "confirming"
    SPEAKING = "speaking"
    THINKING = "thinking"
    ERROR = "error"


class CaptureStage(StrEnum):
    OFF = "off"
    CAPTURING = "capturing"
    ENDPOINTING = "endpointing"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"


class RecognitionStage(StrEnum):
    IDLE = "idle"
    PARTIAL = "partial"
    FINALIZING = "finalizing"
    FINAL = "final"
    CANCELLED = "cancelled"
    FAILED = "failed"


class IntentStage(StrEnum):
    IDLE = "idle"
    SPECULATIVE = "speculative"
    COMMITTED = "committed"
    CONFIRMING = "confirming"
    COMPLETE = "complete"
    FAILED = "failed"


class GenerationStage(StrEnum):
    IDLE = "idle"
    STREAMING = "streaming"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SynthesisStage(StrEnum):
    IDLE = "idle"
    QUEUED = "queued"
    ACTIVE = "active"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PlaybackStage(StrEnum):
    IDLE = "idle"
    BUFFERING = "buffering"
    PLAYING = "playing"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TurnInterruptionState(StrEnum):
    """Whether a turn still owns callbacks and derived output."""

    NONE = "none"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class ProposalState(StrEnum):
    """Whether an untrusted action proposal is ready or ambiguous."""

    READY = "ready"
    AMBIGUOUS = "ambiguous"


class ModularResponseEventKind(StrEnum):
    """Ordered events shared by local and hosted modular text providers."""

    STARTED = "started"
    DELTA = "delta"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VoiceCancellationToken:
    """Thread-safe cooperative cancellation signal owned by one turn."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """Request cancellation from every stage owned by this turn."""
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        return self._event.is_set()


@dataclass(frozen=True, slots=True)
class AudioFrame:
    """One ordered, in-memory PCM frame from a microphone session."""

    session_id: str
    turn_id: str
    sequence_number: int
    captured_at_monotonic: float
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int
    data: bytes = field(repr=False)

    def __post_init__(self) -> None:
        _require_identifier(self.session_id, "session ID")
        _require_identifier(self.turn_id, "turn ID")
        if self.sequence_number < 0:
            raise ValueError("audio frame sequence number cannot be negative.")
        if self.captured_at_monotonic < 0:
            raise ValueError("audio frame timestamp cannot be negative.")
        if self.sample_rate_hz <= 0:
            raise ValueError("audio frame sample rate must be positive.")
        if self.channels <= 0:
            raise ValueError("audio frame channel count must be positive.")
        if self.sample_width_bytes <= 0:
            raise ValueError("audio frame sample width must be positive.")
        if not self.data:
            raise ValueError("audio frame data cannot be empty.")
        if len(self.data) > _MAX_AUDIO_FRAME_BYTES:
            raise ValueError("audio frame data exceeds the one MiB limit.")
        if len(self.data) % self.sample_stride_bytes:
            raise ValueError("audio frame data must end on a PCM sample boundary.")

    @property
    def sample_stride_bytes(self) -> int:
        """Return the byte width of one interleaved PCM sample."""
        return self.channels * self.sample_width_bytes

    @property
    def duration_seconds(self) -> float:
        """Return the duration represented by this frame."""
        return len(self.data) / self.sample_stride_bytes / self.sample_rate_hz


@dataclass(frozen=True, slots=True)
class TranscriptRevision:
    """Ordered recognition text that is replaceable until accepted as final."""

    session_id: str
    turn_id: str
    revision_number: int
    text: str
    status: TranscriptStatus
    provider_name: str
    detected_language: str | None = None
    confidence: TranscriptConfidence = TranscriptConfidence.UNKNOWN
    endpoint_reason: EndpointReason | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.session_id, "session ID")
        _require_identifier(self.turn_id, "turn ID")
        if self.revision_number < 0:
            raise ValueError("transcript revision number cannot be negative.")
        _require_text(self.text, "transcript revision text")
        _require_text(self.provider_name, "transcript provider name", max_chars=128)
        if self.detected_language is not None and not self.detected_language.strip():
            raise ValueError("detected language cannot be blank.")
        if self.status is TranscriptStatus.FINAL and self.endpoint_reason is None:
            raise ValueError("a final transcript requires an endpoint reason.")
        if self.status is TranscriptStatus.PARTIAL and self.endpoint_reason is not None:
            raise ValueError("a partial transcript cannot have an endpoint reason.")


@dataclass(frozen=True, slots=True)
class TurnStages:
    """Concurrent stage snapshots for one conversation turn."""

    capture: CaptureStage = CaptureStage.OFF
    recognition: RecognitionStage = RecognitionStage.IDLE
    intent: IntentStage = IntentStage.IDLE
    generation: GenerationStage = GenerationStage.IDLE
    synthesis: SynthesisStage = SynthesisStage.IDLE
    playback: PlaybackStage = PlaybackStage.IDLE


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """Framework-free ownership snapshot shared across the voice pipeline."""

    session_id: str
    turn_id: str
    cancellation_token: VoiceCancellationToken
    input_mode: VoiceInputMode
    processing_mode: VoiceProcessingMode
    stages: TurnStages = TurnStages()
    accepted_final_transcript: TranscriptRevision | None = None
    latest_transcript_revision: int = -1
    interruption: TurnInterruptionState = TurnInterruptionState.NONE

    def __post_init__(self) -> None:
        _require_identifier(self.session_id, "session ID")
        _require_identifier(self.turn_id, "turn ID")
        if self.latest_transcript_revision < -1:
            raise ValueError("latest transcript revision cannot be less than -1.")
        transcript = self.accepted_final_transcript
        if transcript is not None:
            if transcript.status is not TranscriptStatus.FINAL:
                raise ValueError("accepted transcript must be final.")
            if (transcript.session_id, transcript.turn_id) != (
                self.session_id,
                self.turn_id,
            ):
                raise ValueError("accepted transcript must belong to this turn.")
            if transcript.revision_number != self.latest_transcript_revision:
                raise ValueError("accepted transcript must be the latest revision.")


@dataclass(frozen=True, slots=True)
class LiveSessionConfig:
    """Explicit startup boundary for a provider-neutral live session."""

    session_id: str
    processing_mode: VoiceProcessingMode
    provider_name: str
    input_sample_rate_hz: int
    max_duration_seconds: int

    def __post_init__(self) -> None:
        _require_identifier(self.session_id, "session ID")
        _require_text(
            self.provider_name,
            "live-session provider name",
            max_chars=128,
        )
        if self.input_sample_rate_hz <= 0:
            raise ValueError("live-session sample rate must be positive.")
        if not 1 <= self.max_duration_seconds <= 900:
            raise ValueError("live-session duration must be between 1 and 900 seconds.")


@dataclass(frozen=True, slots=True)
class ModularResponseContext:
    """Identity and selected provider lane for one modular text response."""

    response_id: str
    processing_mode: VoiceProcessingMode
    session_id: str | None = None
    turn_id: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.response_id, "response ID")
        if self.processing_mode is VoiceProcessingMode.HOSTED_LIVE:
            raise ValueError("hosted-live responses require a LiveSessionAdapter.")
        if (self.session_id is None) != (self.turn_id is None):
            raise ValueError("response session and turn IDs must be provided together.")
        if self.session_id is not None:
            _require_identifier(self.session_id, "session ID")
            _require_identifier(self.turn_id or "", "turn ID")


@dataclass(frozen=True, slots=True)
class ModularResponseEvent:
    """One ordered provider-neutral response event on a direct callback path."""

    context: ModularResponseContext
    kind: ModularResponseEventKind
    sequence_number: int
    text: str | None = field(default=None, repr=False)
    error_message: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.sequence_number < 0:
            raise ValueError("response event sequence number cannot be negative.")
        if self.kind is ModularResponseEventKind.STARTED:
            if self.sequence_number != 0:
                raise ValueError("a started response event must have sequence zero.")
            if self.text is not None or self.error_message is not None:
                raise ValueError("a started response event cannot contain output.")
            return
        if self.sequence_number == 0:
            raise ValueError("response events after start require a positive sequence.")
        if self.kind in {
            ModularResponseEventKind.DELTA,
            ModularResponseEventKind.COMPLETED,
        }:
            _require_text(self.text or "", "response event text")
            if self.error_message is not None:
                raise ValueError("a successful response event cannot contain an error.")
            return
        if self.text is not None:
            raise ValueError("failed or cancelled response events cannot contain text.")
        if self.kind is ModularResponseEventKind.FAILED:
            _require_text(
                self.error_message or "",
                "response failure message",
                max_chars=4_096,
            )
        elif self.error_message is not None:
            raise ValueError("a cancelled response event cannot contain an error.")


@dataclass(frozen=True, slots=True)
class CanonicalResponseSegment:
    """One ordered, stable span derived from a modular provider response."""

    response_id: str
    segment_index: int
    canonical_text: str = field(repr=False)
    is_final: bool = False

    def __post_init__(self) -> None:
        _require_identifier(self.response_id, "response ID")
        if self.segment_index < 0:
            raise ValueError("canonical response segment index cannot be negative.")
        _require_text(self.canonical_text, "canonical response segment text")


@dataclass(frozen=True, slots=True)
class AssistantTextRevision:
    """Ordered assistant text emitted by a modular or hosted-live provider."""

    session_id: str
    turn_id: str
    revision_number: int
    text: str
    is_final: bool = False

    def __post_init__(self) -> None:
        _require_identifier(self.session_id, "session ID")
        _require_identifier(self.turn_id, "turn ID")
        if self.revision_number < 0:
            raise ValueError("assistant revision number cannot be negative.")
        _require_text(self.text, "assistant text revision")


@dataclass(frozen=True, slots=True)
class ResponseSegment:
    """One ordered stable text span ready for speech synthesis."""

    session_id: str
    turn_id: str
    segment_index: int
    canonical_text: str
    speech_text: str
    is_final: bool = False

    def __post_init__(self) -> None:
        _require_identifier(self.session_id, "session ID")
        _require_identifier(self.turn_id, "turn ID")
        if self.segment_index < 0:
            raise ValueError("response segment index cannot be negative.")
        _require_text(self.canonical_text, "canonical response text")
        _require_text(self.speech_text, "speech-rendered response text")


@dataclass(frozen=True, slots=True)
class ActionProposal:
    """Untrusted typed action candidate emitted by an intent provider."""

    turn_id: str
    proposal_id: str
    source: str
    action_name: str
    arguments: Mapping[str, object]
    state: ProposalState = ProposalState.READY
    confidence: TranscriptConfidence = TranscriptConfidence.UNKNOWN

    def __post_init__(self) -> None:
        _require_identifier(self.turn_id, "turn ID")
        _require_identifier(self.proposal_id, "proposal ID")
        _require_identifier(self.source, "proposal source")
        _require_identifier(self.action_name, "action name")
        copied_arguments = dict(self.arguments)
        if len(copied_arguments) > _MAX_ACTION_ARGUMENTS:
            raise ValueError("action proposal has too many arguments.")
        for name, value in copied_arguments.items():
            _require_identifier(name, "action argument name")
            if isinstance(value, str):
                if len(value) > _MAX_ACTION_ARGUMENT_TEXT_CHARS:
                    raise ValueError("action proposal argument text is too long.")
            elif not isinstance(value, (bool, int)) and value is not None:
                raise ValueError(
                    "action proposal arguments must be primitive bounded values."
                )
        object.__setattr__(self, "arguments", MappingProxyType(copied_arguments))


@dataclass(frozen=True, slots=True)
class SanitizedActionResult:
    """Bounded action result safe to return to a provider adapter."""

    turn_id: str
    proposal_id: str
    status: str
    message: str

    def __post_init__(self) -> None:
        _require_identifier(self.turn_id, "turn ID")
        _require_identifier(self.proposal_id, "proposal ID")
        _require_text(self.status, "action result status", max_chars=128)
        _require_text(self.message, "action result message", max_chars=4_096)


def _require_identifier(value: str, label: str) -> None:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{label} contains invalid characters.")


def _require_text(value: str, label: str, *, max_chars: int = _MAX_TEXT_CHARS) -> None:
    if not value.strip():
        raise ValueError(f"{label} cannot be empty.")
    if len(value) > max_chars:
        raise ValueError(f"{label} is too long.")
