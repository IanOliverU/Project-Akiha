"""Tests for Qt Multimedia microphone buffering."""

from __future__ import annotations

import unittest
from array import array
from collections.abc import Callable
from typing import Any

from PySide6.QtMultimedia import QAudio, QAudioFormat

from project_akiha.providers.voice import MicrophoneCaptureError
from project_akiha.providers.voice.qt_microphone import QtMicrophoneCapture


class QtMicrophoneCaptureTest(unittest.TestCase):
    """Verify microphone lifecycle without accessing physical hardware."""

    def test_start_and_stop_return_temporary_pcm(self) -> None:
        fixture = _CaptureFixture(chunks=[b"\x00\x01", b"\x02\x03"])
        capture = fixture.build()

        capture.start(
            timeout_seconds=12,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
        )
        fixture.io_device.readyRead.emit()
        audio = capture.stop()

        self.assertEqual(audio.data, b"\x00\x01\x02\x03")
        self.assertEqual(audio.sample_rate_hz, 16_000)
        self.assertEqual(audio.channels, 1)
        self.assertEqual(fixture.timer.started_ms, 12_000)
        self.assertTrue(fixture.source.stopped)
        self.assertFalse(capture.is_capturing)

    def test_uses_requested_pcm_format(self) -> None:
        fixture = _CaptureFixture(chunks=[b"\x00\x01"])
        capture = fixture.build()

        capture.start(
            timeout_seconds=5,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
        )

        audio_format = fixture.audio_format
        assert audio_format is not None
        self.assertEqual(audio_format.sampleRate(), 16_000)
        self.assertEqual(audio_format.channelCount(), 1)
        self.assertEqual(
            audio_format.sampleFormat(),
            QAudioFormat.SampleFormat.Int16,
        )

    def test_timeout_discards_audio_and_releases_device(self) -> None:
        fixture = _CaptureFixture(chunks=[b"\x00\x01"])
        capture = fixture.build()
        timed_out: list[bool] = []
        capture.start(
            timeout_seconds=2,
            on_timeout=lambda: timed_out.append(True),
            on_error=lambda _code, _message: None,
        )

        fixture.timer.timeout.emit()

        self.assertEqual(timed_out, [True])
        self.assertTrue(fixture.source.stopped)
        self.assertFalse(capture.is_capturing)

    def test_device_failure_reports_privacy_safe_error(self) -> None:
        fixture = _CaptureFixture(
            chunks=[b"\x00\x01"],
            source_error=QAudio.Error.IOError,
        )
        capture = fixture.build()
        errors: list[tuple[str, str]] = []
        capture.start(
            timeout_seconds=5,
            on_timeout=lambda: None,
            on_error=lambda code, message: errors.append((code, message)),
        )

        fixture.source.stateChanged.emit(QAudio.State.StoppedState)

        self.assertEqual(errors[0][0], "microphone_device_error")
        self.assertIn("I/O error", errors[0][1])
        self.assertNotIn("00", errors[0][1])
        self.assertFalse(capture.is_capturing)

    def test_cancel_is_idempotent(self) -> None:
        fixture = _CaptureFixture(chunks=[b"\x00\x01"])
        capture = fixture.build()
        capture.start(
            timeout_seconds=5,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
        )

        capture.cancel()
        capture.cancel()

        self.assertFalse(capture.is_capturing)

    def test_rejects_missing_or_unsupported_device(self) -> None:
        missing = _CaptureFixture(device_null=True).build()
        unsupported = _CaptureFixture(format_supported=False).build()

        with self.assertRaisesRegex(MicrophoneCaptureError, "No microphone"):
            missing.start(
                timeout_seconds=5,
                on_timeout=lambda: None,
                on_error=lambda _code, _message: None,
            )

        with self.assertRaisesRegex(MicrophoneCaptureError, "does not support"):
            unsupported.start(
                timeout_seconds=5,
                on_timeout=lambda: None,
                on_error=lambda _code, _message: None,
            )

    def test_rejects_empty_capture(self) -> None:
        fixture = _CaptureFixture(chunks=[])
        capture = fixture.build()
        capture.start(
            timeout_seconds=5,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
        )

        with self.assertRaisesRegex(MicrophoneCaptureError, "No microphone audio"):
            capture.stop()

    def test_device_cannot_change_while_recording(self) -> None:
        fixture = _CaptureFixture(chunks=[b"\x00\x01"])
        capture = fixture.build()
        capture.start(
            timeout_seconds=5,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
        )

        with self.assertRaisesRegex(MicrophoneCaptureError, "Cannot change"):
            capture.set_device_name("Another microphone")

    def test_live_snapshot_and_silence_endpoint_are_local_callbacks(self) -> None:
        speech = _pcm_chunk(1_200, seconds=0.3)
        silence = _pcm_chunk(0, seconds=1.3)
        fixture = _CaptureFixture(chunks=[speech, silence])
        capture = fixture.build()
        snapshots: list[bytes] = []
        silence_events: list[bool] = []
        capture.start(
            timeout_seconds=10,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
            on_audio_snapshot=lambda audio: snapshots.append(audio.data),
            on_silence=lambda: silence_events.append(True),
            live_interval_seconds=0.2,
            silence_timeout_seconds=1.2,
            auto_stop_on_silence=True,
        )

        fixture.io_device.readyRead.emit()
        fixture.io_device.readyRead.emit()

        self.assertEqual(snapshots, [speech, speech + silence])
        self.assertEqual(silence_events, [True])
        self.assertTrue(capture.is_capturing)

    def test_quiet_speech_then_room_noise_reaches_silence_endpoint(self) -> None:
        initial_room_noise = _pcm_chunk(125, seconds=0.25)
        speech = _pcm_chunk(220, seconds=0.3)
        room_noise = _pcm_chunk(125, seconds=3.1)
        fixture = _CaptureFixture(chunks=[initial_room_noise, speech, room_noise])
        capture = fixture.build()
        silence_events: list[bool] = []
        capture.start(
            timeout_seconds=10,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
            on_silence=lambda: silence_events.append(True),
            silence_timeout_seconds=3.0,
            auto_stop_on_silence=True,
        )

        for _ in range(3):
            fixture.io_device.readyRead.emit()

        self.assertEqual(silence_events, [True])

    def test_speech_and_muted_audio_in_one_read_reach_silence_endpoint(self) -> None:
        mixed_chunk = _pcm_chunk(1_200, seconds=0.3) + _pcm_chunk(0, seconds=3.1)
        fixture = _CaptureFixture(chunks=[mixed_chunk])
        capture = fixture.build()
        silence_events: list[bool] = []
        capture.start(
            timeout_seconds=10,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
            on_silence=lambda: silence_events.append(True),
            silence_timeout_seconds=3.0,
            auto_stop_on_silence=True,
        )

        fixture.io_device.readyRead.emit()

        self.assertEqual(silence_events, [True])

    def test_muted_device_with_no_more_audio_uses_wall_clock_endpoint(self) -> None:
        speech = _pcm_chunk(1_200, seconds=0.3)
        fixture = _CaptureFixture(chunks=[speech])
        capture = fixture.build()
        silence_events: list[bool] = []
        capture.start(
            timeout_seconds=10,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
            on_silence=lambda: silence_events.append(True),
            silence_timeout_seconds=3.0,
            auto_stop_on_silence=True,
        )
        fixture.io_device.readyRead.emit()

        fixture.endpoint_timer.timeout.emit()

        self.assertEqual(fixture.endpoint_timer.started_ms, 3_000)
        self.assertEqual(silence_events, [True])

    def test_unaligned_qt_reads_preserve_silence_accounting(self) -> None:
        audio = _pcm_chunk(1_200, seconds=0.3) + _pcm_chunk(0, seconds=3.1)
        chunks = [audio[:777], audio[777:12_345], audio[12_345:]]
        fixture = _CaptureFixture(chunks=chunks)
        capture = fixture.build()
        silence_events: list[bool] = []
        capture.start(
            timeout_seconds=10,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
            on_silence=lambda: silence_events.append(True),
            silence_timeout_seconds=3.0,
            auto_stop_on_silence=True,
        )

        for _ in chunks:
            fixture.io_device.readyRead.emit()

        self.assertEqual(silence_events, [True])

    def test_live_snapshot_continues_during_post_speech_silence(self) -> None:
        speech = _pcm_chunk(1_200, seconds=0.3)
        silence = _pcm_chunk(0, seconds=0.3)
        fixture = _CaptureFixture(chunks=[speech, silence])
        capture = fixture.build()
        snapshots: list[bytes] = []
        capture.start(
            timeout_seconds=10,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
            on_audio_snapshot=lambda audio: snapshots.append(audio.data),
            live_interval_seconds=0.2,
        )

        fixture.io_device.readyRead.emit()
        fixture.io_device.readyRead.emit()

        self.assertEqual(snapshots, [speech, speech + silence])

    def test_live_snapshot_does_not_depend_on_the_volume_gate(self) -> None:
        quiet_audio = _pcm_chunk(80, seconds=1.1)
        fixture = _CaptureFixture(chunks=[quiet_audio])
        capture = fixture.build()
        snapshots: list[bytes] = []
        capture.start(
            timeout_seconds=10,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
            on_audio_snapshot=lambda audio: snapshots.append(audio.data),
            live_interval_seconds=1.0,
        )

        fixture.io_device.readyRead.emit()

        self.assertEqual(snapshots, [quiet_audio])

    def test_brief_noise_spike_does_not_reset_silence_endpoint(self) -> None:
        initial_room_noise = _pcm_chunk(180, seconds=0.25)
        speech = _pcm_chunk(220, seconds=0.3)
        room_noise_before = _pcm_chunk(180, seconds=1.5)
        brief_noise_spike = _pcm_chunk(250, seconds=0.02)
        room_noise_after = _pcm_chunk(180, seconds=1.6)
        fixture = _CaptureFixture(
            chunks=[
                initial_room_noise,
                speech,
                room_noise_before,
                brief_noise_spike,
                room_noise_after,
            ]
        )
        capture = fixture.build()
        silence_events: list[bool] = []
        capture.start(
            timeout_seconds=10,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
            on_silence=lambda: silence_events.append(True),
            silence_timeout_seconds=3.0,
            auto_stop_on_silence=True,
        )

        for _ in range(5):
            fixture.io_device.readyRead.emit()

        self.assertEqual(silence_events, [True])

    def test_steady_fan_noise_does_not_arm_speech_endpoint(self) -> None:
        fan_noise = _pcm_chunk(350, seconds=4.0)
        fixture = _CaptureFixture(chunks=[fan_noise])
        capture = fixture.build()
        silence_events: list[bool] = []
        capture.start(
            timeout_seconds=10,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
            on_silence=lambda: silence_events.append(True),
            silence_timeout_seconds=3.0,
            auto_stop_on_silence=True,
        )

        fixture.io_device.readyRead.emit()
        fixture.endpoint_timer.timeout.emit()

        self.assertEqual(fixture.endpoint_timer.started_ms, 0)
        self.assertEqual(silence_events, [])
        self.assertTrue(capture.is_capturing)

    def test_fan_noise_around_speech_reaches_silence_endpoint(self) -> None:
        fan_noise = _pcm_chunk(350, seconds=0.3)
        speech = _pcm_chunk(600, seconds=0.3)
        trailing_fan_noise = _pcm_chunk(350, seconds=3.1)
        fixture = _CaptureFixture(chunks=[fan_noise, speech, trailing_fan_noise])
        capture = fixture.build()
        silence_events: list[bool] = []
        capture.start(
            timeout_seconds=10,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
            on_silence=lambda: silence_events.append(True),
            silence_timeout_seconds=3.0,
            auto_stop_on_silence=True,
        )

        for _ in range(3):
            fixture.io_device.readyRead.emit()

        self.assertEqual(silence_events, [True])

    def test_loud_immediate_speech_bypasses_noise_calibration(self) -> None:
        speech = _pcm_chunk(600, seconds=0.15)
        silence = _pcm_chunk(0, seconds=1.3)
        fixture = _CaptureFixture(chunks=[speech, silence])
        capture = fixture.build()
        silence_events: list[bool] = []
        capture.start(
            timeout_seconds=10,
            on_timeout=lambda: None,
            on_error=lambda _code, _message: None,
            on_silence=lambda: silence_events.append(True),
            silence_timeout_seconds=1.2,
            auto_stop_on_silence=True,
        )

        fixture.io_device.readyRead.emit()
        fixture.io_device.readyRead.emit()

        self.assertEqual(silence_events, [True])


class _Signal:
    def __init__(self) -> None:
        self._handlers: list[Callable[..., None]] = []

    def connect(self, handler: Callable[..., None]) -> None:
        self._handlers.append(handler)

    def emit(self, *args: object) -> None:
        for handler in tuple(self._handlers):
            handler(*args)


class _FakeTimer:
    def __init__(self) -> None:
        self.timeout = _Signal()
        self.single_shot = False
        self.started_ms = 0
        self.stopped = False

    def setSingleShot(self, single_shot: bool) -> None:
        self.single_shot = single_shot

    def start(self, milliseconds: int) -> None:
        self.started_ms = milliseconds
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _FakeDevice:
    def __init__(self, *, is_null: bool, format_supported: bool) -> None:
        self._is_null = is_null
        self._format_supported = format_supported

    def isNull(self) -> bool:
        return self._is_null

    def isFormatSupported(self, audio_format: QAudioFormat) -> bool:
        del audio_format
        return self._format_supported


class _FakeIODevice:
    def __init__(self, chunks: list[bytes]) -> None:
        self.readyRead = _Signal()
        self._chunks = chunks

    def readAll(self) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class _FakeSource:
    def __init__(
        self,
        io_device: _FakeIODevice,
        source_error: QAudio.Error,
    ) -> None:
        self.stateChanged = _Signal()
        self._io_device = io_device
        self._error = source_error
        self.stopped = False

    def start(self) -> _FakeIODevice:
        return self._io_device

    def stop(self) -> None:
        self.stopped = True

    def error(self) -> QAudio.Error:
        return self._error


class _CaptureFixture:
    def __init__(
        self,
        *,
        chunks: list[bytes] | None = None,
        device_null: bool = False,
        format_supported: bool = True,
        source_error: QAudio.Error = QAudio.Error.NoError,
    ) -> None:
        self.timer = _FakeTimer()
        self.endpoint_timer = _FakeTimer()
        self.device = _FakeDevice(
            is_null=device_null,
            format_supported=format_supported,
        )
        self.io_device = _FakeIODevice(list(chunks or []))
        self.source = _FakeSource(self.io_device, source_error)
        self.audio_format: QAudioFormat | None = None

    def build(self) -> QtMicrophoneCapture:
        def build_source(
            _device: Any,
            audio_format: QAudioFormat,
            _parent: Any,
        ) -> _FakeSource:
            self.audio_format = audio_format
            return self.source

        return QtMicrophoneCapture(
            device_resolver=lambda _name: self.device,
            source_factory=build_source,
            timer_factory=lambda _parent: self.timer,
            endpoint_timer_factory=lambda _parent: self.endpoint_timer,
        )


def _pcm_chunk(amplitude: int, *, seconds: float) -> bytes:
    sample_count = int(16_000 * seconds)
    samples = array("h", [amplitude]) * sample_count
    return samples.tobytes()


if __name__ == "__main__":
    unittest.main()
