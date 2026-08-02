"""Lazy local speech recognition through faster-whisper."""

from __future__ import annotations

import asyncio
import wave
from collections.abc import Callable
from io import BytesIO
from math import exp, isfinite
from pathlib import Path
from threading import Lock
from typing import Any

from project_akiha.providers.voice.base import (
    CapturedAudio,
    VoiceProviderError,
    VoiceProviderHealth,
    VoiceProviderStatus,
    VoiceTranscript,
)

_COMMAND_HOTWORDS = (
    "Akiha Spotify Discord Chrome Visual Studio Code VS Code VLC VOICEVOX"
)


class FasterWhisperProvider:
    """Transcribe in-memory PCM with a lazily loaded CPU Whisper model."""

    def __init__(
        self,
        model_size: str,
        language: str,
        download_root: Path,
        *,
        model_class_loader: Callable[[], Any] | None = None,
    ) -> None:
        self._model_size = model_size
        self._language = None if language == "auto" else language
        self._download_root = download_root
        self._model_class_loader = model_class_loader or _load_model_class
        self._model: Any | None = None
        self._model_lock = Lock()

    async def health(self) -> VoiceProviderHealth:
        """Check dependency availability without downloading a model."""
        try:
            await asyncio.to_thread(self._model_class_loader)
        except (ImportError, OSError) as error:
            return VoiceProviderHealth(
                VoiceProviderStatus.UNAVAILABLE,
                f"faster-whisper is unavailable: {error}",
            )
        except Exception as error:
            return VoiceProviderHealth(
                VoiceProviderStatus.UNAVAILABLE,
                f"faster-whisper could not be loaded: {error}",
            )
        return VoiceProviderHealth(
            VoiceProviderStatus.AVAILABLE,
            "faster-whisper is installed; the model loads on first use.",
        )

    async def transcribe(self, audio: CapturedAudio) -> VoiceTranscript:
        """Transcribe captured PCM away from the caller's event loop."""
        return await asyncio.to_thread(self._transcribe_sync, audio)

    def _transcribe_sync(self, audio: CapturedAudio) -> VoiceTranscript:
        wav_stream = _captured_audio_to_wav(audio)
        model = self._get_model()
        try:
            segments, info = model.transcribe(
                wav_stream,
                language=self._language,
                beam_size=1,
                vad_filter=True,
                hotwords=_COMMAND_HOTWORDS,
            )
            resolved_segments = tuple(segments)
            text = "".join(str(segment.text) for segment in resolved_segments).strip()
        except VoiceProviderError:
            raise
        except Exception as error:
            raise VoiceProviderError(
                "transcription_failed",
                f"Local speech recognition failed: {error}",
            ) from error

        if not text:
            raise VoiceProviderError(
                "empty_transcript",
                "No speech was recognized in the recording.",
            )

        detected_language = getattr(info, "language", None)
        if not isinstance(detected_language, str):
            detected_language = self._language
        return VoiceTranscript(
            text=text,
            detected_language=detected_language,
            confidence=_aggregate_segment_confidence(resolved_segments),
        )

    def _get_model(self) -> Any:
        with self._model_lock:
            if self._model is not None:
                return self._model

            try:
                model_class = self._model_class_loader()
                self._download_root.mkdir(parents=True, exist_ok=True)
                self._model = model_class(
                    self._model_size,
                    device="cpu",
                    compute_type="int8",
                    download_root=str(self._download_root),
                )
            except (ImportError, OSError) as error:
                raise VoiceProviderError(
                    "provider_unavailable",
                    f"faster-whisper is unavailable: {error}",
                ) from error
            except Exception as error:
                raise VoiceProviderError(
                    "model_load_failed",
                    f"The local Whisper model could not be loaded: {error}",
                ) from error
            return self._model


def _captured_audio_to_wav(audio: CapturedAudio) -> BytesIO:
    stream = BytesIO()
    try:
        with wave.open(stream, "wb") as wav_file:
            wav_file.setnchannels(audio.channels)
            wav_file.setsampwidth(audio.sample_width_bytes)
            wav_file.setframerate(audio.sample_rate_hz)
            wav_file.writeframes(audio.data)
    except (wave.Error, OSError) as error:
        raise VoiceProviderError(
            "invalid_audio",
            f"Captured audio could not be prepared for transcription: {error}",
        ) from error
    stream.seek(0)
    return stream


def _aggregate_segment_confidence(segments: tuple[object, ...]) -> float | None:
    weighted_total = 0.0
    total_weight = 0
    for segment in segments:
        avg_logprob = getattr(segment, "avg_logprob", None)
        no_speech_prob = getattr(segment, "no_speech_prob", None)
        if (
            not isinstance(avg_logprob, (int, float))
            or isinstance(avg_logprob, bool)
            or not isfinite(float(avg_logprob))
        ):
            continue
        if (
            not isinstance(no_speech_prob, (int, float))
            or isinstance(no_speech_prob, bool)
            or not isfinite(float(no_speech_prob))
        ):
            no_speech_prob = 0.0

        speech_probability = 1.0 - min(1.0, max(0.0, float(no_speech_prob)))
        token_probability = exp(min(0.0, float(avg_logprob)))
        confidence = min(
            1.0,
            max(
                0.0,
                0.8 * token_probability + 0.2 * speech_probability,
            ),
        )
        weight = max(1, len(str(getattr(segment, "text", "")).strip()))
        weighted_total += confidence * weight
        total_weight += weight

    if total_weight == 0:
        return None
    return min(1.0, max(0.0, weighted_total / total_weight))


def _load_model_class() -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel
