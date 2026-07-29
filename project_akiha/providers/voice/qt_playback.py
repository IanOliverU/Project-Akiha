"""In-memory synthesized audio playback through Qt Multimedia."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QUrl
from PySide6.QtMultimedia import (
    QAudioDevice,
    QAudioOutput,
    QMediaDevices,
    QMediaPlayer,
)

from project_akiha.providers.voice.base import (
    AudioPlaybackError,
    SynthesizedAudio,
)


class QtAudioPlayback(QObject):
    """Play one temporary WAV from memory and release it deterministically."""

    def __init__(
        self,
        device_name: str = "",
        volume_percent: int = 100,
        parent: QObject | None = None,
        *,
        device_resolver: Callable[[str], Any] | None = None,
        player_factory: Callable[[QObject], Any] | None = None,
        audio_output_factory: Callable[[QObject], Any] | None = None,
        buffer_factory: Callable[[QObject], Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self._device_name = device_name
        self._volume_percent = _validate_volume(volume_percent)
        self._device_resolver = device_resolver or _resolve_output_device
        self._buffer_factory = buffer_factory or QBuffer

        self._audio_output = (audio_output_factory or QAudioOutput)(self)
        self._player = (player_factory or QMediaPlayer)(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.playbackStateChanged.connect(self._handle_playback_state)
        self._player.mediaStatusChanged.connect(self._handle_media_status)
        self._player.errorOccurred.connect(self._handle_error)

        self._buffer: Any | None = None
        self._started = False
        self._cleaning_up = False
        self._on_started: Callable[[], None] | None = None
        self._on_finished: Callable[[], None] | None = None
        self._on_error: Callable[[str, str], None] | None = None

    @property
    def is_active(self) -> bool:
        """Return whether encoded audio is currently retained."""
        return self._buffer is not None

    def apply_settings(self, device_name: str, volume_percent: int) -> None:
        """Apply output settings for the next playback."""
        validated_volume = _validate_volume(volume_percent)
        if self.is_active:
            self.stop()
        self._device_name = device_name
        self._volume_percent = validated_volume

    def play(
        self,
        audio: SynthesizedAudio,
        *,
        on_started: Callable[[], None],
        on_finished: Callable[[], None],
        on_error: Callable[[str, str], None],
    ) -> None:
        """Load one WAV into a QBuffer and begin playback."""
        if self.is_active:
            raise AudioPlaybackError(
                "playback_busy",
                "Speech playback is already active.",
            )
        if audio.media_type.partition(";")[0].strip().lower() not in {
            "audio/wav",
            "audio/x-wav",
        }:
            raise AudioPlaybackError(
                "unsupported_audio_format",
                "Speech playback requires WAV audio.",
            )

        device = self._device_resolver(self._device_name)
        if device.isNull():
            raise AudioPlaybackError(
                "output_device_unavailable",
                "No audio output device is available.",
            )

        buffer = self._buffer_factory(self)
        try:
            buffer.setData(QByteArray(audio.data))
            if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
                raise AudioPlaybackError(
                    "audio_buffer_open_failed",
                    "Synthesized audio could not be opened for playback.",
                )
            self._audio_output.setDevice(device)
            self._audio_output.setVolume(self._volume_percent / 100.0)
            self._buffer = buffer
            self._started = False
            self._on_started = on_started
            self._on_finished = on_finished
            self._on_error = on_error
            self._player.setSourceDevice(buffer, QUrl("akiha-voice.wav"))
            self._player.play()
        except AudioPlaybackError:
            if self._buffer is buffer:
                self._buffer = None
            self._discard_buffer(buffer)
            self._clear_callbacks()
            raise
        except Exception as error:
            if self._buffer is buffer:
                self._buffer = None
            self._discard_buffer(buffer)
            self._clear_callbacks()
            raise AudioPlaybackError(
                "playback_start_failed",
                f"Speech playback failed to start: {error}",
            ) from error

    def stop(self) -> None:
        """Stop playback and release the in-memory WAV."""
        if not self.is_active:
            return
        self._player.stop()
        self._cleanup()

    def _handle_playback_state(
        self,
        state: QMediaPlayer.PlaybackState,
    ) -> None:
        if (
            state != QMediaPlayer.PlaybackState.PlayingState
            or not self.is_active
            or self._started
        ):
            return
        self._started = True
        callback = self._on_started
        if callback is not None:
            callback()

    def _handle_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if not self.is_active:
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            callback = self._on_finished
            self._cleanup()
            if callback is not None:
                callback()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._finish_with_error(
                "invalid_playback_media",
                "Synthesized audio could not be played.",
            )

    def _handle_error(
        self,
        error: QMediaPlayer.Error,
        error_string: str,
    ) -> None:
        if not self.is_active or error == QMediaPlayer.Error.NoError:
            return
        detail = error_string.strip() or "Qt Multimedia reported a playback error."
        self._finish_with_error("playback_device_error", detail)

    def _finish_with_error(self, code: str, message: str) -> None:
        callback = self._on_error
        self._cleanup()
        if callback is not None:
            callback(code, message)

    def _cleanup(self) -> None:
        if self._cleaning_up:
            return
        self._cleaning_up = True
        try:
            buffer = self._buffer
            self._buffer = None
            self._started = False
            self._player.setSource(QUrl())
            self._discard_buffer(buffer)
            self._clear_callbacks()
        finally:
            self._cleaning_up = False

    def _clear_callbacks(self) -> None:
        self._on_started = None
        self._on_finished = None
        self._on_error = None

    @staticmethod
    def _discard_buffer(buffer: Any | None) -> None:
        if buffer is None:
            return
        buffer.close()
        if isinstance(buffer, QObject):
            buffer.deleteLater()


def _validate_volume(volume_percent: int) -> int:
    if not 0 <= volume_percent <= 100:
        raise AudioPlaybackError(
            "invalid_playback_volume",
            "Speech playback volume must be between 0 and 100.",
        )
    return volume_percent


def _resolve_output_device(device_name: str) -> QAudioDevice:
    requested_name = device_name.strip().casefold()
    if not requested_name:
        return QMediaDevices.defaultAudioOutput()

    for device in QMediaDevices.audioOutputs():
        if device.description().strip().casefold() == requested_name:
            return device
    return QAudioDevice()
