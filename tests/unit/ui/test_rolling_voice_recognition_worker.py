"""Tests for the Qt rolling-recognition worker handoff."""

from __future__ import annotations

import unittest

from project_akiha.core.voice_session import AudioFrame, EndpointReason
from project_akiha.services.speech_input import SpeechInputServiceError
from project_akiha.ui.rolling_voice_recognition_worker import (
    RollingVoiceRecognitionThread,
)


class RollingVoiceRecognitionThreadTest(unittest.TestCase):
    def test_processes_frames_in_order_then_finalizes(self) -> None:
        recognizer = _Recognizer()
        worker = RollingVoiceRecognitionThread(
            recognizer,  # type: ignore[arg-type]
            (_frame(0), _frame(1)),
            EndpointReason.SILENCE,
        )

        worker.run()

        self.assertEqual(recognizer.sequences, [0, 1])
        self.assertEqual(recognizer.partial_sequences, [])
        self.assertEqual(recognizer.endpoint_reasons, [EndpointReason.SILENCE])

    def test_partial_batch_buffers_backlog_and_recognizes_only_latest(self) -> None:
        recognizer = _Recognizer()
        worker = RollingVoiceRecognitionThread(
            recognizer,  # type: ignore[arg-type]
            tuple(_frame(sequence) for sequence in range(6)),
        )

        worker.run()

        self.assertEqual(recognizer.sequences, list(range(6)))
        self.assertEqual(recognizer.partial_sequences, [5])

    def test_latest_partial_failure_is_reported_after_buffering_backlog(self) -> None:
        recognizer = _Recognizer(fail_sequence=1)
        worker = RollingVoiceRecognitionThread(
            recognizer,  # type: ignore[arg-type]
            (_frame(0), _frame(1)),
        )
        failures: list[tuple[str, str]] = []
        worker.recognition_failed.connect(
            lambda code, message: failures.append((code, message))
        )

        worker.run()

        self.assertEqual(recognizer.sequences, [0, 1])
        self.assertEqual(recognizer.partial_sequences, [1])
        self.assertEqual(failures[0][0], "temporary_failure")

    def test_cancel_before_run_does_not_process_audio(self) -> None:
        recognizer = _Recognizer()
        worker = RollingVoiceRecognitionThread(
            recognizer,  # type: ignore[arg-type]
            (_frame(0),),
        )
        cancelled: list[bool] = []
        worker.recognition_cancelled.connect(lambda: cancelled.append(True))

        worker.cancel()
        worker.run()

        self.assertTrue(recognizer.cancelled)
        self.assertEqual(recognizer.sequences, [])
        self.assertEqual(cancelled, [True])


class _Recognizer:
    def __init__(self, *, fail_sequence: int | None = None) -> None:
        self.fail_sequence = fail_sequence
        self.sequences: list[int] = []
        self.partial_sequences: list[int] = []
        self.endpoint_reasons: list[EndpointReason] = []
        self.cancelled = False

    async def accept_audio(self, frame: AudioFrame) -> None:
        self.sequences.append(frame.sequence_number)
        self.partial_sequences.append(frame.sequence_number)
        if frame.sequence_number == self.fail_sequence:
            raise SpeechInputServiceError(
                "temporary_failure",
                "Temporary recognition failure.",
            )

    def buffer_audio(self, frame: AudioFrame) -> None:
        self.sequences.append(frame.sequence_number)

    async def finalize(self, endpoint_reason: EndpointReason) -> None:
        self.endpoint_reasons.append(endpoint_reason)

    def cancel(self) -> None:
        self.cancelled = True


def _frame(sequence_number: int) -> AudioFrame:
    return AudioFrame(
        session_id="session-1",
        turn_id="turn-1",
        sequence_number=sequence_number,
        captured_at_monotonic=float(sequence_number),
        sample_rate_hz=16_000,
        channels=1,
        sample_width_bytes=2,
        data=bytes(3_200),
    )


if __name__ == "__main__":
    unittest.main()
