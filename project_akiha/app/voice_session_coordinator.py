"""Application-owned lifecycle and stage coordination for voice sessions."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace

from project_akiha.core.voice_session import (
    CaptureStage,
    ConversationTurn,
    GenerationStage,
    IntentStage,
    PlaybackStage,
    RecognitionStage,
    SessionLifecycle,
    SynthesisStage,
    TranscriptRevision,
    VoiceInputMode,
    VoiceProcessingMode,
    VoiceSessionCue,
    VoiceStage,
    VoiceTurnLedger,
)

StageState = (
    CaptureStage
    | RecognitionStage
    | IntentStage
    | GenerationStage
    | SynthesisStage
    | PlaybackStage
)
SessionObserver = Callable[["VoiceSessionSnapshot"], None]


class InvalidVoiceSessionTransitionError(ValueError):
    """Raised when lifecycle or concurrent-stage progression is illegal."""


@dataclass(frozen=True, slots=True)
class VoiceSessionSnapshot:
    """Immutable coordinator state safe for UI and diagnostic observers."""

    lifecycle: SessionLifecycle
    session_id: str | None
    processing_mode: VoiceProcessingMode | None
    active_turn: ConversationTurn | None
    dominant_cue: VoiceSessionCue
    error_code: str | None = None


class VoiceSessionCoordinator:
    """Own session lifecycle, turn identity, stage state, and cancellation."""

    _LIFECYCLE_TRANSITIONS = {
        SessionLifecycle.IDLE: frozenset({SessionLifecycle.STARTING}),
        SessionLifecycle.STARTING: frozenset(
            {
                SessionLifecycle.ACTIVE,
                SessionLifecycle.STOPPING,
                SessionLifecycle.ERROR,
            }
        ),
        SessionLifecycle.ACTIVE: frozenset(
            {SessionLifecycle.STOPPING, SessionLifecycle.ERROR}
        ),
        SessionLifecycle.ERROR: frozenset({SessionLifecycle.STOPPING}),
        SessionLifecycle.STOPPING: frozenset({SessionLifecycle.IDLE}),
    }
    _STAGE_TYPES = {
        VoiceStage.CAPTURE: CaptureStage,
        VoiceStage.RECOGNITION: RecognitionStage,
        VoiceStage.INTENT: IntentStage,
        VoiceStage.GENERATION: GenerationStage,
        VoiceStage.SYNTHESIS: SynthesisStage,
        VoiceStage.PLAYBACK: PlaybackStage,
    }
    _STAGE_TRANSITIONS = {
        VoiceStage.CAPTURE: {
            CaptureStage.OFF: frozenset(
                {CaptureStage.CAPTURING, CaptureStage.CANCELLED, CaptureStage.FAILED}
            ),
            CaptureStage.CAPTURING: frozenset(
                {
                    CaptureStage.ENDPOINTING,
                    CaptureStage.COMPLETE,
                    CaptureStage.CANCELLED,
                    CaptureStage.FAILED,
                }
            ),
            CaptureStage.ENDPOINTING: frozenset(
                {
                    CaptureStage.COMPLETE,
                    CaptureStage.CANCELLED,
                    CaptureStage.FAILED,
                }
            ),
            CaptureStage.COMPLETE: frozenset(),
            CaptureStage.CANCELLED: frozenset(),
            CaptureStage.FAILED: frozenset(),
        },
        VoiceStage.RECOGNITION: {
            RecognitionStage.IDLE: frozenset(
                {
                    RecognitionStage.PARTIAL,
                    RecognitionStage.FINALIZING,
                    RecognitionStage.FINAL,
                    RecognitionStage.CANCELLED,
                    RecognitionStage.FAILED,
                }
            ),
            RecognitionStage.PARTIAL: frozenset(
                {
                    RecognitionStage.PARTIAL,
                    RecognitionStage.FINALIZING,
                    RecognitionStage.FINAL,
                    RecognitionStage.CANCELLED,
                    RecognitionStage.FAILED,
                }
            ),
            RecognitionStage.FINALIZING: frozenset(
                {
                    RecognitionStage.FINAL,
                    RecognitionStage.CANCELLED,
                    RecognitionStage.FAILED,
                }
            ),
            RecognitionStage.FINAL: frozenset(),
            RecognitionStage.CANCELLED: frozenset(),
            RecognitionStage.FAILED: frozenset(),
        },
        VoiceStage.INTENT: {
            IntentStage.IDLE: frozenset(
                {IntentStage.SPECULATIVE, IntentStage.COMMITTED, IntentStage.FAILED}
            ),
            IntentStage.SPECULATIVE: frozenset(
                {
                    IntentStage.SPECULATIVE,
                    IntentStage.COMMITTED,
                    IntentStage.CONFIRMING,
                    IntentStage.FAILED,
                }
            ),
            IntentStage.COMMITTED: frozenset(
                {
                    IntentStage.CONFIRMING,
                    IntentStage.COMPLETE,
                    IntentStage.FAILED,
                }
            ),
            IntentStage.CONFIRMING: frozenset(
                {IntentStage.COMMITTED, IntentStage.COMPLETE, IntentStage.FAILED}
            ),
            IntentStage.COMPLETE: frozenset(),
            IntentStage.FAILED: frozenset(),
        },
        VoiceStage.GENERATION: {
            GenerationStage.IDLE: frozenset(
                {
                    GenerationStage.STREAMING,
                    GenerationStage.COMPLETE,
                    GenerationStage.CANCELLED,
                    GenerationStage.FAILED,
                }
            ),
            GenerationStage.STREAMING: frozenset(
                {
                    GenerationStage.COMPLETE,
                    GenerationStage.CANCELLED,
                    GenerationStage.FAILED,
                }
            ),
            GenerationStage.COMPLETE: frozenset(),
            GenerationStage.CANCELLED: frozenset(),
            GenerationStage.FAILED: frozenset(),
        },
        VoiceStage.SYNTHESIS: {
            SynthesisStage.IDLE: frozenset(
                {
                    SynthesisStage.QUEUED,
                    SynthesisStage.ACTIVE,
                    SynthesisStage.CANCELLED,
                    SynthesisStage.FAILED,
                }
            ),
            SynthesisStage.QUEUED: frozenset(
                {
                    SynthesisStage.ACTIVE,
                    SynthesisStage.COMPLETE,
                    SynthesisStage.CANCELLED,
                    SynthesisStage.FAILED,
                }
            ),
            SynthesisStage.ACTIVE: frozenset(
                {
                    SynthesisStage.COMPLETE,
                    SynthesisStage.CANCELLED,
                    SynthesisStage.FAILED,
                }
            ),
            SynthesisStage.COMPLETE: frozenset(),
            SynthesisStage.CANCELLED: frozenset(),
            SynthesisStage.FAILED: frozenset(),
        },
        VoiceStage.PLAYBACK: {
            PlaybackStage.IDLE: frozenset(
                {
                    PlaybackStage.BUFFERING,
                    PlaybackStage.PLAYING,
                    PlaybackStage.CANCELLED,
                    PlaybackStage.FAILED,
                }
            ),
            PlaybackStage.BUFFERING: frozenset(
                {
                    PlaybackStage.PLAYING,
                    PlaybackStage.COMPLETE,
                    PlaybackStage.CANCELLED,
                    PlaybackStage.FAILED,
                }
            ),
            PlaybackStage.PLAYING: frozenset(
                {
                    PlaybackStage.COMPLETE,
                    PlaybackStage.CANCELLED,
                    PlaybackStage.FAILED,
                }
            ),
            PlaybackStage.COMPLETE: frozenset(),
            PlaybackStage.CANCELLED: frozenset(),
            PlaybackStage.FAILED: frozenset(),
        },
    }

    def __init__(
        self,
        *,
        session_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._session_id_factory = session_id_factory or (lambda: uuid.uuid4().hex)
        self._lifecycle = SessionLifecycle.IDLE
        self._processing_mode: VoiceProcessingMode | None = None
        self._ledger: VoiceTurnLedger | None = None
        self._error_code: str | None = None
        self._observers: list[SessionObserver] = []

    @property
    def snapshot(self) -> VoiceSessionSnapshot:
        """Return the current immutable coordinator state."""
        with self._lock:
            return self._snapshot()

    def subscribe(self, observer: SessionObserver) -> None:
        """Observe future state changes without transferring ownership."""
        with self._lock:
            if observer not in self._observers:
                self._observers.append(observer)

    def unsubscribe(self, observer: SessionObserver) -> None:
        """Remove a previously registered observer."""
        with self._lock:
            if observer in self._observers:
                self._observers.remove(observer)

    def request_start(
        self,
        processing_mode: VoiceProcessingMode,
    ) -> VoiceSessionSnapshot:
        """Reserve a new session before microphone or provider readiness."""
        with self._lock:
            self._transition_lifecycle(SessionLifecycle.STARTING)
            session_id = self._session_id_factory()
            self._ledger = VoiceTurnLedger(session_id)
            self._processing_mode = processing_mode
            self._error_code = None
            snapshot = self._snapshot()
        self._notify(snapshot)
        return snapshot

    def activate(self) -> VoiceSessionSnapshot:
        """Mark that the selected microphone or provider lane is ready."""
        return self._change_lifecycle(SessionLifecycle.ACTIVE)

    def begin_turn(self, input_mode: VoiceInputMode) -> ConversationTurn:
        """Begin one authoritative turn in the explicitly selected lane."""
        with self._lock:
            ledger, processing_mode = self._require_active_session()
            turn = ledger.begin_turn(
                input_mode=input_mode,
                processing_mode=processing_mode,
            )
            snapshot = self._snapshot()
        self._notify(snapshot)
        return turn

    def replace_turn(self, input_mode: VoiceInputMode) -> ConversationTurn:
        """Interrupt current work before assigning callback ownership anew."""
        with self._lock:
            ledger, processing_mode = self._require_active_session()
            turn = ledger.replace_turn(
                input_mode=input_mode,
                processing_mode=processing_mode,
            )
            snapshot = self._snapshot()
        self._notify(snapshot)
        return turn

    def accepts_callback(self, session_id: str, turn_id: str) -> bool:
        """Return whether the callback still belongs to this active session."""
        with self._lock:
            return (
                self._lifecycle is SessionLifecycle.ACTIVE
                and self._ledger is not None
                and self._ledger.accepts_callback(session_id, turn_id)
            )

    def get_turn(self, turn_id: str) -> ConversationTurn | None:
        """Return one historical turn snapshot without restoring its authority."""
        with self._lock:
            if self._ledger is None:
                return None
            return self._ledger.get_turn(turn_id)

    def accept_transcript_revision(self, revision: TranscriptRevision) -> bool:
        """Accept an ordered partial or final transcript from the active turn."""
        with self._lock:
            if self._lifecycle is not SessionLifecycle.ACTIVE or self._ledger is None:
                return False
            accepted = self._ledger.accept_transcript_revision(revision)
            snapshot = self._snapshot() if accepted else None
        if snapshot is not None:
            self._notify(snapshot)
        return accepted

    def transition_stage(
        self,
        session_id: str,
        turn_id: str,
        stage: VoiceStage,
        next_state: StageState,
    ) -> bool:
        """Advance one stage without forcing unrelated stages to wait."""
        with self._lock:
            if not self.accepts_callback(session_id, turn_id):
                return False
            expected_type = self._STAGE_TYPES[stage]
            if not isinstance(next_state, expected_type):
                raise TypeError(f"{stage.value} requires {expected_type.__name__}.")

            assert self._ledger is not None
            turn = self._ledger.active_turn
            assert turn is not None
            current_state = getattr(turn.stages, stage.value)
            if next_state == current_state:
                return True
            if next_state not in self._STAGE_TRANSITIONS[stage][current_state]:
                raise InvalidVoiceSessionTransitionError(
                    f"Cannot transition {stage.value} from {current_state} "
                    f"to {next_state}."
                )
            if (
                stage is VoiceStage.INTENT
                and next_state
                in {IntentStage.COMMITTED, IntentStage.CONFIRMING, IntentStage.COMPLETE}
                and turn.accepted_final_transcript is None
            ):
                raise InvalidVoiceSessionTransitionError(
                    "Intent cannot commit before a final transcript is accepted."
                )

            stages = replace(turn.stages, **{stage.value: next_state})
            changed = self._ledger.replace_active_stages(
                session_id,
                turn_id,
                stages,
            )
            snapshot = self._snapshot() if changed else None
        if snapshot is not None:
            self._notify(snapshot)
        return changed

    def complete_turn(self, session_id: str, turn_id: str) -> bool:
        """Release turn authority so late callbacks cannot mutate state."""
        with self._lock:
            if not self.accepts_callback(session_id, turn_id):
                return False
            assert self._ledger is not None
            self._ledger.complete_active()
            snapshot = self._snapshot()
        self._notify(snapshot)
        return True

    def cancel_active_turn(self) -> ConversationTurn | None:
        """Cancel all active stages while leaving the session available."""
        with self._lock:
            if self._ledger is None:
                return None
            turn = self._ledger.cancel_active()
            snapshot = self._snapshot() if turn is not None else None
        if snapshot is not None:
            self._notify(snapshot)
        return turn

    def report_error(self, code: str) -> VoiceSessionSnapshot:
        """Enter a sanitized error state and cancel active turn ownership."""
        cleaned_code = code.strip() or "voice_session_error"
        with self._lock:
            self._transition_lifecycle(SessionLifecycle.ERROR)
            self._error_code = cleaned_code
            if self._ledger is not None:
                self._ledger.cancel_active()
            snapshot = self._snapshot()
        self._notify(snapshot)
        return snapshot

    def request_stop(self) -> VoiceSessionSnapshot:
        """Begin bounded cleanup and reject every owned callback."""
        with self._lock:
            if self._lifecycle is SessionLifecycle.IDLE:
                return self._snapshot()
            if self._lifecycle is not SessionLifecycle.STOPPING:
                self._transition_lifecycle(SessionLifecycle.STOPPING)
            if self._ledger is not None:
                self._ledger.close()
            snapshot = self._snapshot()
        self._notify(snapshot)
        return snapshot

    def finish_stop(self) -> VoiceSessionSnapshot:
        """Release session identity after external resources finish cleanup."""
        with self._lock:
            if self._lifecycle is SessionLifecycle.IDLE:
                return self._snapshot()
            self._transition_lifecycle(SessionLifecycle.IDLE)
            self._ledger = None
            self._processing_mode = None
            self._error_code = None
            snapshot = self._snapshot()
        self._notify(snapshot)
        return snapshot

    def close(self) -> VoiceSessionSnapshot:
        """Idempotently cancel and release the complete session."""
        self.request_stop()
        return self.finish_stop()

    def _change_lifecycle(
        self,
        lifecycle: SessionLifecycle,
    ) -> VoiceSessionSnapshot:
        with self._lock:
            self._transition_lifecycle(lifecycle)
            snapshot = self._snapshot()
        self._notify(snapshot)
        return snapshot

    def _transition_lifecycle(self, lifecycle: SessionLifecycle) -> None:
        if lifecycle is self._lifecycle:
            return
        if lifecycle not in self._LIFECYCLE_TRANSITIONS[self._lifecycle]:
            raise InvalidVoiceSessionTransitionError(
                f"Cannot transition session from {self._lifecycle} to {lifecycle}."
            )
        self._lifecycle = lifecycle

    def _require_active_session(
        self,
    ) -> tuple[VoiceTurnLedger, VoiceProcessingMode]:
        if (
            self._lifecycle is not SessionLifecycle.ACTIVE
            or self._ledger is None
            or self._processing_mode is None
        ):
            raise RuntimeError("voice session is not active.")
        return self._ledger, self._processing_mode

    def _snapshot(self) -> VoiceSessionSnapshot:
        active_turn = self._ledger.active_turn if self._ledger is not None else None
        return VoiceSessionSnapshot(
            lifecycle=self._lifecycle,
            session_id=self._ledger.session_id if self._ledger is not None else None,
            processing_mode=self._processing_mode,
            active_turn=active_turn,
            dominant_cue=_derive_dominant_cue(self._lifecycle, active_turn),
            error_code=self._error_code,
        )

    def _notify(self, snapshot: VoiceSessionSnapshot) -> None:
        with self._lock:
            observers = tuple(self._observers)
        for observer in observers:
            observer(snapshot)


def _derive_dominant_cue(
    lifecycle: SessionLifecycle,
    turn: ConversationTurn | None,
) -> VoiceSessionCue:
    if lifecycle is SessionLifecycle.ERROR:
        return VoiceSessionCue.ERROR
    if turn is None:
        return VoiceSessionCue.IDLE
    stages = turn.stages
    if stages.capture in {CaptureStage.CAPTURING, CaptureStage.ENDPOINTING}:
        return VoiceSessionCue.LISTENING
    if stages.intent is IntentStage.CONFIRMING:
        return VoiceSessionCue.CONFIRMING
    if stages.playback in {PlaybackStage.BUFFERING, PlaybackStage.PLAYING}:
        return VoiceSessionCue.SPEAKING
    if (
        stages.recognition is RecognitionStage.FINALIZING
        or stages.intent in {IntentStage.COMMITTED, IntentStage.COMPLETE}
        or stages.generation is GenerationStage.STREAMING
        or stages.synthesis in {SynthesisStage.QUEUED, SynthesisStage.ACTIVE}
    ):
        return VoiceSessionCue.THINKING
    return VoiceSessionCue.IDLE
