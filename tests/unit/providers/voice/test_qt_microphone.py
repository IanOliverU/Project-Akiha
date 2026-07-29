"""Tests for Qt Multimedia microphone buffering."""

from __future__ import annotations

import unittest
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
        )


if __name__ == "__main__":
    unittest.main()
