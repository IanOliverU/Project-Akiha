"""Tests for in-memory Qt synthesized audio playback."""

from __future__ import annotations

import unittest
from collections.abc import Callable

from PySide6.QtCore import QObject
from PySide6.QtMultimedia import QMediaPlayer

from project_akiha.providers.voice import (
    AudioPlaybackError,
    SynthesizedAudio,
)
from project_akiha.providers.voice.qt_playback import QtAudioPlayback


class QtAudioPlaybackTest(unittest.TestCase):
    """Verify playback state, device settings, and buffer cleanup."""

    def test_play_starts_wav_from_memory_with_selected_settings(self) -> None:
        playback, player, output, buffers = _build()
        started: list[bool] = []

        playback.play(
            _audio(),
            on_started=lambda: started.append(True),
            on_finished=lambda: None,
            on_error=lambda _code, _message: None,
        )
        player.playbackStateChanged.emit(QMediaPlayer.PlaybackState.PlayingState)

        self.assertTrue(playback.is_active)
        self.assertEqual(bytes(buffers[0].data), b"RIFFprivate-wave")
        self.assertTrue(buffers[0].opened)
        self.assertIs(player.source_device, buffers[0])
        self.assertEqual(output.device.description(), "Desktop speakers")
        self.assertEqual(output.volume, 0.75)
        self.assertTrue(player.play_called)
        self.assertEqual(started, [True])

    def test_playing_signal_notifies_started_only_once(self) -> None:
        playback, player, _, _ = _build()
        started: list[bool] = []
        playback.play(
            _audio(),
            on_started=lambda: started.append(True),
            on_finished=lambda: None,
            on_error=lambda _code, _message: None,
        )

        player.playbackStateChanged.emit(QMediaPlayer.PlaybackState.PlayingState)
        player.playbackStateChanged.emit(QMediaPlayer.PlaybackState.PlayingState)

        self.assertEqual(started, [True])

    def test_end_of_media_finishes_and_releases_buffer(self) -> None:
        playback, player, _, buffers = _build()
        finished: list[bool] = []
        playback.play(
            _audio(),
            on_started=lambda: None,
            on_finished=lambda: finished.append(True),
            on_error=lambda _code, _message: None,
        )

        player.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.EndOfMedia)

        self.assertFalse(playback.is_active)
        self.assertEqual(finished, [True])
        self.assertTrue(buffers[0].closed)
        self.assertTrue(buffers[0].deleted)
        self.assertTrue(player.source.isEmpty())

    def test_stop_releases_buffer_without_completion_callback(self) -> None:
        playback, player, _, buffers = _build()
        finished: list[bool] = []
        playback.play(
            _audio(),
            on_started=lambda: None,
            on_finished=lambda: finished.append(True),
            on_error=lambda _code, _message: None,
        )

        playback.stop()

        self.assertTrue(player.stop_called)
        self.assertFalse(playback.is_active)
        self.assertTrue(buffers[0].closed)
        self.assertEqual(finished, [])

    def test_invalid_media_reports_error_once_and_releases_buffer(self) -> None:
        playback, player, _, buffers = _build()
        errors: list[tuple[str, str]] = []
        playback.play(
            _audio(),
            on_started=lambda: None,
            on_finished=lambda: None,
            on_error=lambda code, message: errors.append((code, message)),
        )

        player.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.InvalidMedia)
        player.errorOccurred.emit(
            QMediaPlayer.Error.FormatError,
            "duplicate backend error",
        )

        self.assertEqual(errors[0][0], "invalid_playback_media")
        self.assertEqual(len(errors), 1)
        self.assertTrue(buffers[0].closed)

    def test_device_error_reports_safe_detail_and_releases_buffer(self) -> None:
        playback, player, _, buffers = _build()
        errors: list[tuple[str, str]] = []
        playback.play(
            _audio(),
            on_started=lambda: None,
            on_finished=lambda: None,
            on_error=lambda code, message: errors.append((code, message)),
        )

        player.errorOccurred.emit(
            QMediaPlayer.Error.ResourceError,
            "Output device disconnected.",
        )

        self.assertEqual(
            errors,
            [("playback_device_error", "Output device disconnected.")],
        )
        self.assertTrue(buffers[0].closed)

    def test_missing_output_device_rejects_playback(self) -> None:
        playback, _, _, buffers = _build(device=_Device("", is_null=True))

        with self.assertRaises(AudioPlaybackError) as captured:
            playback.play(
                _audio(),
                on_started=lambda: None,
                on_finished=lambda: None,
                on_error=lambda _code, _message: None,
            )

        self.assertEqual(captured.exception.code, "output_device_unavailable")
        self.assertEqual(buffers, [])

    def test_overlapping_playback_is_rejected(self) -> None:
        playback, _, _, _ = _build()
        callbacks = {
            "on_started": lambda: None,
            "on_finished": lambda: None,
            "on_error": lambda _code, _message: None,
        }
        playback.play(_audio(), **callbacks)

        with self.assertRaises(AudioPlaybackError) as captured:
            playback.play(_audio(), **callbacks)

        self.assertEqual(captured.exception.code, "playback_busy")

    def test_settings_change_stops_active_playback(self) -> None:
        playback, player, output, _ = _build()
        playback.play(
            _audio(),
            on_started=lambda: None,
            on_finished=lambda: None,
            on_error=lambda _code, _message: None,
        )

        playback.apply_settings("Headphones", 40)
        playback.play(
            _audio(),
            on_started=lambda: None,
            on_finished=lambda: None,
            on_error=lambda _code, _message: None,
        )

        self.assertTrue(player.stop_called)
        self.assertEqual(output.device.description(), "Desktop speakers")
        self.assertEqual(output.volume, 0.4)

    def test_non_wav_audio_is_rejected(self) -> None:
        playback, _, _, _ = _build()

        with self.assertRaises(AudioPlaybackError) as captured:
            playback.play(
                SynthesizedAudio(b"encoded", "audio/mpeg"),
                on_started=lambda: None,
                on_finished=lambda: None,
                on_error=lambda _code, _message: None,
            )

        self.assertEqual(captured.exception.code, "unsupported_audio_format")


class _Signal:
    def __init__(self) -> None:
        self.handlers: list[Callable[..., None]] = []

    def connect(self, handler: Callable[..., None]) -> None:
        self.handlers.append(handler)

    def emit(self, *args: object) -> None:
        for handler in tuple(self.handlers):
            handler(*args)


class _Player:
    def __init__(self, parent: QObject) -> None:
        del parent
        self.playbackStateChanged = _Signal()
        self.mediaStatusChanged = _Signal()
        self.errorOccurred = _Signal()
        self.audio_output: object | None = None
        self.source_device: object | None = None
        self.source = _Url()
        self.play_called = False
        self.stop_called = False

    def setAudioOutput(self, output: object) -> None:
        self.audio_output = output

    def setSourceDevice(self, device: object, url: object) -> None:
        self.source_device = device
        self.source = url

    def setSource(self, url: object) -> None:
        self.source_device = None
        self.source = url

    def play(self) -> None:
        self.play_called = True

    def stop(self) -> None:
        self.stop_called = True


class _AudioOutput:
    def __init__(self, parent: QObject) -> None:
        del parent
        self.device = _Device("", is_null=True)
        self.volume = 1.0

    def setDevice(self, device: _Device) -> None:
        self.device = device

    def setVolume(self, volume: float) -> None:
        self.volume = volume


class _Buffer(QObject):
    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self.data = b""
        self.opened = False
        self.closed = False
        self.deleted = False

    def setData(self, data: object) -> None:
        self.data = bytes(data)

    def open(self, mode: object) -> bool:
        del mode
        self.opened = True
        return True

    def close(self) -> None:
        self.closed = True

    def deleteLater(self) -> None:
        self.deleted = True


class _Device:
    def __init__(self, description: str, *, is_null: bool = False) -> None:
        self._description = description
        self._is_null = is_null

    def isNull(self) -> bool:
        return self._is_null

    def description(self) -> str:
        return self._description


class _Url:
    def isEmpty(self) -> bool:
        return True


def _build(
    *,
    device: _Device | None = None,
) -> tuple[QtAudioPlayback, _Player, _AudioOutput, list[_Buffer]]:
    player = _Player(QObject())
    output = _AudioOutput(QObject())
    buffers: list[_Buffer] = []
    selected_device = device or _Device("Desktop speakers")

    def build_buffer(parent: QObject) -> _Buffer:
        buffer = _Buffer(parent)
        buffers.append(buffer)
        return buffer

    playback = QtAudioPlayback(
        device_name="Desktop speakers",
        volume_percent=75,
        device_resolver=lambda _name: selected_device,
        player_factory=lambda _parent: player,
        audio_output_factory=lambda _parent: output,
        buffer_factory=build_buffer,
    )
    return playback, player, output, buffers


def _audio() -> SynthesizedAudio:
    return SynthesizedAudio(b"RIFFprivate-wave", "audio/wav", 24_000)


if __name__ == "__main__":
    unittest.main()
