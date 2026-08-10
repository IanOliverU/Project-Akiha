"""Qt Multimedia microphone capture for push-to-talk."""

from __future__ import annotations

from array import array
from collections.abc import Callable
from math import ceil, sqrt
from statistics import median
from sys import byteorder
from typing import Any

from PySide6.QtCore import QObject, QTimer
from PySide6.QtMultimedia import (
    QAudio,
    QAudioDevice,
    QAudioFormat,
    QAudioSource,
    QMediaDevices,
)

from project_akiha.providers.voice.base import (
    CapturedAudio,
    MicrophoneActivity,
    MicrophoneCaptureError,
)

_SAMPLE_RATE_HZ = 16_000
_CHANNELS = 1
_SAMPLE_WIDTH_BYTES = 2
_SPEECH_START_RMS_THRESHOLD = 160.0
_SILENCE_MINIMUM_RMS_THRESHOLD = 120.0
_NOISE_CALIBRATION_SECONDS = 0.2
_NOISE_FLOOR_DEFAULT_RMS = 80.0
_NOISE_FLOOR_UPDATE_WEIGHT = 0.08
_SPEECH_NOISE_RATIO = 1.15
_SPEECH_NOISE_MARGIN = 30.0
_SILENCE_NOISE_RATIO = 1.1
_SILENCE_NOISE_MARGIN = 20.0
_SILENCE_PEAK_RATIO = 0.35
_IMMEDIATE_SPEECH_RMS_THRESHOLD = 500.0
_IMMEDIATE_SPEECH_SECONDS = 0.1
_MINIMUM_SPEECH_SECONDS = 0.25
_CONTINUED_SPEECH_SECONDS = 0.1
_ANALYSIS_FRAME_SECONDS = 0.02
_ANALYSIS_FRAME_BYTES = int(
    _SAMPLE_RATE_HZ * _CHANNELS * _SAMPLE_WIDTH_BYTES * _ANALYSIS_FRAME_SECONDS
)


class QtMicrophoneCapture(QObject):
    """Capture temporary 16 kHz mono PCM through Qt Multimedia."""

    def __init__(
        self,
        device_name: str = "",
        parent: QObject | None = None,
        *,
        device_resolver: Callable[[str], Any] | None = None,
        source_factory: Callable[[Any, QAudioFormat, QObject], Any] | None = None,
        timer_factory: Callable[[QObject], Any] | None = None,
        endpoint_timer_factory: Callable[[QObject], Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self._device_name = device_name
        self._device_resolver = device_resolver or _resolve_input_device
        self._source_factory = source_factory or _build_audio_source
        self._timer = (timer_factory or QTimer)(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._handle_timeout)
        self._endpoint_timer = (endpoint_timer_factory or QTimer)(self)
        self._endpoint_timer.setSingleShot(True)
        self._endpoint_timer.timeout.connect(self._handle_silence_timeout)

        self._source: Any | None = None
        self._io_device: Any | None = None
        self._buffer = bytearray()
        self._analysis_buffer = bytearray()
        self._is_capturing = False
        self._on_timeout: Callable[[], None] | None = None
        self._on_error: Callable[[str, str], None] | None = None
        self._on_audio_frame: Callable[[CapturedAudio], None] | None = None
        self._on_audio_snapshot: Callable[[CapturedAudio], None] | None = None
        self._on_silence: Callable[[], None] | None = None
        self._on_activity: Callable[[MicrophoneActivity], None] | None = None
        self._last_activity: MicrophoneActivity | None = None
        self._live_interval_bytes = 0
        self._next_snapshot_bytes = 0
        self._silence_timeout_bytes = 0
        self._silence_timeout_ms = 0
        self._speech_bytes = 0
        self._silence_bytes = 0
        self._continued_speech_bytes = 0
        self._peak_speech_rms = 0.0
        self._noise_calibration_bytes = 0
        self._noise_calibration_samples: list[float] = []
        self._noise_floor_rms = _NOISE_FLOOR_DEFAULT_RMS
        self._has_speech = False
        self._auto_stop_on_silence = False
        self._endpoint_requested = False

    @property
    def is_capturing(self) -> bool:
        """Return whether push-to-talk capture is active."""
        return self._is_capturing

    def set_device_name(self, device_name: str) -> None:
        """Select an input device for the next capture."""
        if self._is_capturing:
            raise MicrophoneCaptureError(
                "capture_busy",
                "Cannot change microphone while capture is active.",
            )
        self._device_name = device_name

    def start(
        self,
        *,
        timeout_seconds: int,
        on_timeout: Callable[[], None],
        on_error: Callable[[str, str], None],
        on_audio_frame: Callable[[CapturedAudio], None] | None = None,
        on_audio_snapshot: Callable[[CapturedAudio], None] | None = None,
        on_silence: Callable[[], None] | None = None,
        on_activity: Callable[[MicrophoneActivity], None] | None = None,
        live_interval_seconds: float = 1.0,
        silence_timeout_seconds: float = 1.2,
        auto_stop_on_silence: bool = False,
    ) -> None:
        """Start a bounded push-to-talk recording."""
        if self._is_capturing:
            raise MicrophoneCaptureError(
                "capture_busy",
                "Microphone capture is already active.",
            )
        if timeout_seconds <= 0:
            raise MicrophoneCaptureError(
                "invalid_capture_timeout",
                "Microphone capture timeout must be greater than zero.",
            )
        if live_interval_seconds <= 0:
            raise MicrophoneCaptureError(
                "invalid_live_interval",
                "Live transcription interval must be greater than zero.",
            )
        if silence_timeout_seconds <= 0:
            raise MicrophoneCaptureError(
                "invalid_silence_timeout",
                "Silence timeout must be greater than zero.",
            )

        device = self._device_resolver(self._device_name)
        if device.isNull():
            raise MicrophoneCaptureError(
                "microphone_unavailable",
                "No microphone input device is available.",
            )

        audio_format = _build_audio_format()
        if not device.isFormatSupported(audio_format):
            raise MicrophoneCaptureError(
                "microphone_format_unsupported",
                "The selected microphone does not support 16 kHz mono audio.",
            )

        self._buffer.clear()
        self._analysis_buffer.clear()
        self._on_timeout = on_timeout
        self._on_error = on_error
        self._on_audio_frame = on_audio_frame
        self._on_audio_snapshot = on_audio_snapshot
        self._on_silence = on_silence
        self._on_activity = on_activity
        self._last_activity = None
        bytes_per_second = _SAMPLE_RATE_HZ * _CHANNELS * _SAMPLE_WIDTH_BYTES
        self._live_interval_bytes = max(
            _SAMPLE_WIDTH_BYTES,
            int(bytes_per_second * live_interval_seconds),
        )
        self._next_snapshot_bytes = self._live_interval_bytes
        self._silence_timeout_bytes = max(
            _SAMPLE_WIDTH_BYTES,
            int(bytes_per_second * silence_timeout_seconds),
        )
        self._silence_timeout_ms = max(1, round(silence_timeout_seconds * 1000))
        self._speech_bytes = 0
        self._silence_bytes = 0
        self._continued_speech_bytes = 0
        self._peak_speech_rms = 0.0
        self._noise_calibration_bytes = 0
        self._noise_calibration_samples.clear()
        self._noise_floor_rms = _NOISE_FLOOR_DEFAULT_RMS
        self._has_speech = False
        self._auto_stop_on_silence = auto_stop_on_silence
        self._endpoint_requested = False
        try:
            self._source = self._source_factory(device, audio_format, self)
            self._source.stateChanged.connect(self._handle_source_state_changed)
            self._is_capturing = True
            self._io_device = self._source.start()
            if self._io_device is None:
                raise MicrophoneCaptureError(
                    "microphone_open_failed",
                    "The selected microphone could not be opened.",
                )
            self._io_device.readyRead.connect(self._read_available)
            self._timer.start(timeout_seconds * 1000)
        except MicrophoneCaptureError:
            self._cleanup()
            raise
        except Exception as error:
            self._cleanup()
            raise MicrophoneCaptureError(
                "microphone_start_failed",
                f"Microphone capture failed to start: {error}",
            ) from error

    def stop(self) -> CapturedAudio:
        """Stop capture and return the accumulated temporary PCM data."""
        if not self._is_capturing:
            raise MicrophoneCaptureError(
                "capture_not_active",
                "Microphone capture is not active.",
            )

        try:
            self._read_available()
            captured = bytes(self._buffer)
        except Exception as error:
            self._cleanup()
            raise MicrophoneCaptureError(
                "microphone_read_failed",
                f"Microphone capture could not be read: {error}",
            ) from error

        self._cleanup()
        if not captured:
            raise MicrophoneCaptureError(
                "empty_capture",
                "No microphone audio was captured.",
            )
        return CapturedAudio(
            data=captured,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            channels=_CHANNELS,
            sample_width_bytes=_SAMPLE_WIDTH_BYTES,
        )

    def cancel(self) -> None:
        """Discard temporary PCM data and release the microphone."""
        if not self._is_capturing and self._source is None:
            return
        self._cleanup()

    def _read_available(self) -> None:
        if self._io_device is None:
            return
        chunk = bytes(self._io_device.readAll())
        if chunk:
            self._buffer.extend(chunk)
            self._process_audio_chunk(chunk)

    def _process_audio_chunk(self, chunk: bytes) -> None:
        self._analysis_buffer.extend(chunk)
        while len(self._analysis_buffer) >= _ANALYSIS_FRAME_BYTES:
            frame = bytes(self._analysis_buffer[:_ANALYSIS_FRAME_BYTES])
            del self._analysis_buffer[:_ANALYSIS_FRAME_BYTES]
            self._process_audio_frame(frame)
            if not self._is_capturing:
                return

        if (
            self._on_audio_snapshot is not None
            and len(self._buffer) >= self._next_snapshot_bytes
        ):
            self._on_audio_snapshot(self._snapshot())
            while len(self._buffer) >= self._next_snapshot_bytes:
                self._next_snapshot_bytes += self._live_interval_bytes

    def _process_audio_frame(self, frame: bytes) -> None:
        callback = self._on_audio_frame
        if callback is not None:
            try:
                callback(
                    CapturedAudio(
                        data=frame,
                        sample_rate_hz=_SAMPLE_RATE_HZ,
                        channels=_CHANNELS,
                        sample_width_bytes=_SAMPLE_WIDTH_BYTES,
                    )
                )
            except Exception:
                error_callback = self._on_error
                self._cleanup()
                if error_callback is not None:
                    error_callback(
                        "microphone_stream_failed",
                        "Live microphone audio could not be delivered.",
                    )
                return
        frame_size = len(frame)
        rms = _pcm_rms(frame)
        if not self._has_speech:
            self._process_pre_speech_frame(rms, frame_size)
        elif rms >= self._speech_release_threshold():
            self._peak_speech_rms = max(self._peak_speech_rms, rms)
            self._continued_speech_bytes += frame_size
            continued_speech_bytes = int(
                _SAMPLE_RATE_HZ
                * _CHANNELS
                * _SAMPLE_WIDTH_BYTES
                * _CONTINUED_SPEECH_SECONDS
            )
            if self._continued_speech_bytes >= continued_speech_bytes:
                self._silence_bytes = 0
                self._continued_speech_bytes = 0
                if self._auto_stop_on_silence:
                    self._endpoint_timer.start(self._silence_timeout_ms)
        elif self._has_speech:
            self._continued_speech_bytes = 0
            self._silence_bytes += frame_size
            self._update_noise_floor(rms)

        self._emit_activity(rms)

        if (
            self._auto_stop_on_silence
            and self._has_speech
            and not self._endpoint_requested
            and self._silence_bytes >= self._silence_timeout_bytes
        ):
            self._request_silence_endpoint()

    def _process_pre_speech_frame(self, rms: float, frame_size: int) -> None:
        calibration_bytes = int(
            _SAMPLE_RATE_HZ
            * _CHANNELS
            * _SAMPLE_WIDTH_BYTES
            * _NOISE_CALIBRATION_SECONDS
        )
        if self._noise_calibration_bytes < calibration_bytes:
            self._noise_calibration_bytes += frame_size
            if rms < _IMMEDIATE_SPEECH_RMS_THRESHOLD:
                self._noise_calibration_samples.append(rms)
                self._speech_bytes = 0
            else:
                self._speech_bytes += frame_size

            if self._noise_calibration_bytes >= calibration_bytes:
                self._finish_noise_calibration()
            if self._speech_bytes >= self._duration_bytes(_IMMEDIATE_SPEECH_SECONDS):
                self._mark_speech_started(rms)
            return

        if rms >= self._speech_start_threshold():
            self._peak_speech_rms = max(self._peak_speech_rms, rms)
            self._speech_bytes += frame_size
            if self._speech_bytes >= self._duration_bytes(_MINIMUM_SPEECH_SECONDS):
                self._mark_speech_started(rms)
            return

        self._speech_bytes = 0
        self._peak_speech_rms = 0.0
        self._update_noise_floor(rms)

    def _finish_noise_calibration(self) -> None:
        if self._noise_calibration_samples:
            self._noise_floor_rms = max(
                1.0,
                float(median(self._noise_calibration_samples)),
            )
        else:
            self._noise_floor_rms = _NOISE_FLOOR_DEFAULT_RMS

    def _speech_start_threshold(self) -> float:
        return max(
            _SPEECH_START_RMS_THRESHOLD,
            self._noise_floor_rms * _SPEECH_NOISE_RATIO,
            self._noise_floor_rms + _SPEECH_NOISE_MARGIN,
        )

    def _speech_release_threshold(self) -> float:
        return max(
            _SILENCE_MINIMUM_RMS_THRESHOLD,
            self._noise_floor_rms * _SILENCE_NOISE_RATIO,
            self._noise_floor_rms + _SILENCE_NOISE_MARGIN,
            self._peak_speech_rms * _SILENCE_PEAK_RATIO,
        )

    def _mark_speech_started(self, rms: float) -> None:
        self._has_speech = True
        self._peak_speech_rms = max(self._peak_speech_rms, rms)
        self._speech_bytes = 0
        self._silence_bytes = 0
        self._continued_speech_bytes = 0
        if self._auto_stop_on_silence:
            self._endpoint_timer.start(self._silence_timeout_ms)

    def _update_noise_floor(self, rms: float) -> None:
        self._noise_floor_rms = (
            1.0 - _NOISE_FLOOR_UPDATE_WEIGHT
        ) * self._noise_floor_rms + _NOISE_FLOOR_UPDATE_WEIGHT * rms

    def _emit_activity(self, rms: float) -> None:
        callback = self._on_activity
        if callback is None:
            return

        calibration_bytes = self._duration_bytes(_NOISE_CALIBRATION_SECONDS)
        release_threshold = self._speech_release_threshold()
        if self._noise_calibration_bytes < calibration_bytes and not self._has_speech:
            activity = "calibrating"
        elif not self._has_speech:
            activity = "waiting"
        elif rms >= release_threshold:
            activity = "speaking"
        else:
            activity = "pause"

        start_threshold = self._speech_start_threshold()
        if rms >= start_threshold * 2.0:
            level = "loud"
        elif rms >= release_threshold:
            level = "speech"
        elif rms >= max(1.0, self._noise_floor_rms * 0.65):
            level = "ambient"
        else:
            level = "quiet"

        silence_remaining: float | None = None
        if activity == "pause" and self._auto_stop_on_silence:
            elapsed = self._silence_bytes / (
                _SAMPLE_RATE_HZ * _CHANNELS * _SAMPLE_WIDTH_BYTES
            )
            remaining = max(0.0, self._silence_timeout_ms / 1000.0 - elapsed)
            silence_remaining = ceil(remaining * 10.0) / 10.0

        snapshot = MicrophoneActivity(
            activity=activity,
            level=level,
            silence_remaining_seconds=silence_remaining,
        )
        if snapshot == self._last_activity:
            return
        self._last_activity = snapshot
        callback(snapshot)

    @staticmethod
    def _duration_bytes(seconds: float) -> int:
        return int(_SAMPLE_RATE_HZ * _CHANNELS * _SAMPLE_WIDTH_BYTES * seconds)

    def _snapshot(self) -> CapturedAudio:
        return CapturedAudio(
            data=bytes(self._buffer),
            sample_rate_hz=_SAMPLE_RATE_HZ,
            channels=_CHANNELS,
            sample_width_bytes=_SAMPLE_WIDTH_BYTES,
        )

    def _handle_timeout(self) -> None:
        if not self._is_capturing:
            return
        callback = self._on_timeout
        self._cleanup()
        if callback is not None:
            callback()

    def _handle_silence_timeout(self) -> None:
        if (
            self._is_capturing
            and self._auto_stop_on_silence
            and self._has_speech
            and not self._endpoint_requested
        ):
            self._request_silence_endpoint()

    def _request_silence_endpoint(self) -> None:
        self._endpoint_requested = True
        self._endpoint_timer.stop()
        callback = self._on_silence
        if callback is not None:
            callback()

    def _handle_source_state_changed(self, state: QAudio.State) -> None:
        if not self._is_capturing or state != QAudio.State.StoppedState:
            return

        error = self._source.error() if self._source is not None else None
        callback = self._on_error
        detail = _audio_error_message(error)
        self._cleanup()
        if callback is not None:
            callback("microphone_device_error", detail)

    def _cleanup(self) -> None:
        self._is_capturing = False
        self._timer.stop()
        self._endpoint_timer.stop()
        source = self._source
        self._source = None
        self._io_device = None
        self._on_timeout = None
        self._on_error = None
        self._on_audio_frame = None
        self._on_audio_snapshot = None
        self._on_silence = None
        self._on_activity = None
        self._last_activity = None
        self._live_interval_bytes = 0
        self._next_snapshot_bytes = 0
        self._silence_timeout_bytes = 0
        self._silence_timeout_ms = 0
        self._speech_bytes = 0
        self._silence_bytes = 0
        self._continued_speech_bytes = 0
        self._peak_speech_rms = 0.0
        self._noise_calibration_bytes = 0
        self._noise_calibration_samples.clear()
        self._noise_floor_rms = _NOISE_FLOOR_DEFAULT_RMS
        self._has_speech = False
        self._auto_stop_on_silence = False
        self._endpoint_requested = False
        self._buffer.clear()
        self._analysis_buffer.clear()
        if source is not None:
            source.stop()
            if isinstance(source, QObject):
                source.deleteLater()


def _build_audio_format() -> QAudioFormat:
    audio_format = QAudioFormat()
    audio_format.setSampleRate(_SAMPLE_RATE_HZ)
    audio_format.setChannelCount(_CHANNELS)
    audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    return audio_format


def _pcm_rms(data: bytes) -> float:
    sample_bytes = len(data) - (len(data) % _SAMPLE_WIDTH_BYTES)
    if sample_bytes == 0:
        return 0.0
    samples = array("h")
    samples.frombytes(data[:sample_bytes])
    if byteorder != "little":
        samples.byteswap()
    return sqrt(sum(sample * sample for sample in samples) / len(samples))


def _resolve_input_device(device_name: str) -> QAudioDevice:
    requested_name = device_name.strip().casefold()
    if not requested_name:
        return QMediaDevices.defaultAudioInput()

    for device in QMediaDevices.audioInputs():
        if device.description().strip().casefold() == requested_name:
            return device
    return QAudioDevice()


def _build_audio_source(
    device: QAudioDevice,
    audio_format: QAudioFormat,
    parent: QObject,
) -> QAudioSource:
    return QAudioSource(device, audio_format, parent)


def _audio_error_message(error: QAudio.Error | None) -> str:
    messages = {
        QAudio.Error.OpenError: "The microphone could not be opened.",
        QAudio.Error.IOError: "The microphone stopped because of an I/O error.",
        QAudio.Error.UnderrunError: "The microphone audio buffer underrun.",
        QAudio.Error.FatalError: "The microphone stopped after a fatal error.",
        QAudio.Error.NoError: "The microphone stopped unexpectedly.",
    }
    return messages.get(error, "The microphone stopped unexpectedly.")
