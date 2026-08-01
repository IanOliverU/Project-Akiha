"""Coordinated cancellation and shutdown for the V0 bridge prototypes."""

from __future__ import annotations

from dataclasses import dataclass

from spikes.voice_pipeline.action_gateway_probe import TypedActionGatewayProbe
from spikes.voice_pipeline.qt_audio_bridge import QtSnapshotAudioFrameBridge
from spikes.voice_pipeline.rolling_recognizer import RollingTranscriptRecognizer
from spikes.voice_pipeline.voicevox_processor import OrderedVoiceVoxProcessor


@dataclass(frozen=True, slots=True)
class BridgeShutdownReport:
    """Privacy-safe result of releasing one active V0 turn."""

    turn_id: int | None
    capture_released: bool
    recognition_released: bool
    action_invalidated: bool
    output_released: bool
    errors: tuple[str, ...] = ()


class VoiceBridgeSessionProbe:
    """Own turn identity while existing bridge objects own their resources."""

    def __init__(
        self,
        audio_frames: QtSnapshotAudioFrameBridge,
        recognizer: RollingTranscriptRecognizer,
        actions: TypedActionGatewayProbe,
        output: OrderedVoiceVoxProcessor,
    ) -> None:
        self._audio_frames = audio_frames
        self._recognizer = recognizer
        self._actions = actions
        self._output = output
        self._active_turn_id: int | None = None
        self._closed = False

    @property
    def active_turn_id(self) -> int | None:
        return self._active_turn_id

    @property
    def is_closed(self) -> bool:
        return self._closed

    def activate(self, turn_id: int) -> None:
        """Track one turn after its individual bridges have been started."""
        if self._closed:
            raise RuntimeError("Voice bridge session is shut down.")
        if isinstance(turn_id, bool) or not isinstance(turn_id, int) or turn_id < 1:
            raise ValueError("Voice bridge turn ID must be positive.")
        if self._active_turn_id is not None:
            raise RuntimeError("Voice bridge session already owns a turn.")
        self._active_turn_id = turn_id

    async def cancel_active_turn(self) -> BridgeShutdownReport:
        """Release every bridge for the current turn and permit a later turn."""
        return await self._release_active_turn()

    async def shutdown(self) -> BridgeShutdownReport:
        """Permanently reject new turns and release every active bridge."""
        if self._closed:
            return BridgeShutdownReport(
                turn_id=None,
                capture_released=not self._audio_frames.is_active,
                recognition_released=not self._recognizer.is_active,
                action_invalidated=True,
                output_released=not self._output.is_active,
            )
        self._closed = True
        report = await self._release_active_turn()
        self._actions.shutdown()
        return report

    async def _release_active_turn(self) -> BridgeShutdownReport:
        turn_id = self._active_turn_id
        errors: list[str] = []
        action_invalidated = turn_id is None
        output_released = not self._output.is_active

        if turn_id is not None:
            try:
                action_invalidated = self._actions.cancel_turn(turn_id)
            except Exception:
                errors.append("action")
            try:
                if self._output.is_active:
                    await self._output.cancel_turn(turn_id)
                output_released = not self._output.is_active
            except Exception:
                errors.append("output")

        try:
            self._audio_frames.stop()
        except Exception:
            errors.append("capture")
        try:
            self._recognizer.cancel()
        except Exception:
            errors.append("recognition")

        self._active_turn_id = None
        return BridgeShutdownReport(
            turn_id=turn_id,
            capture_released=not self._audio_frames.is_active,
            recognition_released=not self._recognizer.is_active,
            action_invalidated=action_invalidated,
            output_released=output_released,
            errors=tuple(errors),
        )
