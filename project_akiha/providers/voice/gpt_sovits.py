"""GPT-SoVITS HTTP speech synthesis provider.

This module is deliberately only an HTTP client.  GPT-SoVITS may run as a
managed local subprocess later, but Project Akiha does not depend on its UI or
on a particular model directory layout.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import wave
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from project_akiha.providers.voice.base import (
    SpeechSynthesisRequest,
    SynthesizedAudio,
    VoiceOption,
    VoiceProviderError,
    VoiceProviderHealth,
    VoiceProviderStatus,
)


class GptSoVitsTransportError(RuntimeError):
    """A local GPT-SoVITS HTTP failure with a stable diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code.strip() or "gpt_sovits_transport_error"


class GptSoVitsTransport(Protocol):
    """Synchronous transport run outside the asyncio event loop."""

    def request_bytes(
        self,
        method: str,
        url: str,
        *,
        operation: str,
        payload: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> tuple[bytes, str]:
        """Return response bytes and its media type."""


class GptSoVitsProvider:
    """Call an Akiha GPT-SoVITS voice through the official local API."""

    voice_identifier = "akiha"

    def __init__(
        self,
        api_url: str = "http://127.0.0.1:9880",
        reference_audio_path: Path | None = None,
        *,
        prompt_text: str = "",
        prompt_language: str = "ja",
        timeout_seconds: float = 60.0,
        temperature: float = 0.8,
        top_k: int = 15,
        top_p: float = 0.9,
        transport: GptSoVitsTransport | None = None,
    ) -> None:
        if not api_url.strip():
            raise ValueError("GPT-SoVITS API URL cannot be empty.")
        if timeout_seconds <= 0:
            raise ValueError("GPT-SoVITS timeout must be greater than zero.")
        if temperature <= 0:
            raise ValueError("GPT-SoVITS temperature must be positive.")
        if top_k < 1:
            raise ValueError("GPT-SoVITS top_k must be positive.")
        if not 0.0 < top_p <= 1.0:
            raise ValueError("GPT-SoVITS top_p must be between zero and one.")
        self._api_url = api_url.rstrip("/")
        self._reference_audio_path = reference_audio_path
        self._prompt_text = prompt_text.strip()
        self._prompt_language = prompt_language.strip() or "ja"
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._top_k = top_k
        self._top_p = top_p
        self._transport = transport or UrllibGptSoVitsTransport()

    async def health(self) -> VoiceProviderHealth:
        """Check the local API and the configured reference prompt audio."""
        if (
            self._reference_audio_path is None
            or not self._reference_audio_path.is_file()
        ):
            return VoiceProviderHealth(
                VoiceProviderStatus.UNAVAILABLE,
                "GPT-SoVITS reference prompt audio is not configured.",
            )
        try:
            data, media_type = await self._request_bytes(
                "GET", "/", operation="health check"
            )
        except VoiceProviderError as error:
            # The official GPT-SoVITS API does not register a root handler,
            # so Uvicorn/FastAPI correctly answers GET / with 404 while the
            # synthesis endpoint is still healthy.
            if error.code == "gpt_sovits_http_error" and "HTTP 404" in str(error):
                return VoiceProviderHealth(
                    VoiceProviderStatus.AVAILABLE,
                    "GPT-SoVITS local API is reachable.",
                )
            return VoiceProviderHealth(VoiceProviderStatus.UNAVAILABLE, str(error))
        if media_type.startswith("application/json") and data:
            return VoiceProviderHealth(
                VoiceProviderStatus.AVAILABLE,
                "GPT-SoVITS local API is reachable.",
            )
        return VoiceProviderHealth(
            VoiceProviderStatus.AVAILABLE,
            "GPT-SoVITS local API is reachable.",
        )

    async def available_voices(self) -> Sequence[VoiceOption]:
        """Expose the one configured reference identity."""
        health = await self.health()
        if health.status != VoiceProviderStatus.AVAILABLE:
            raise VoiceProviderError("provider_unavailable", health.detail)
        return (
            VoiceOption(
                identifier=self.voice_identifier,
                name="Akiha (GPT-SoVITS reference voice)",
                language="ja-JP",
            ),
        )

    async def synthesize(
        self,
        request: SpeechSynthesisRequest,
    ) -> SynthesizedAudio:
        """Generate one WAV utterance without blocking the application loop."""
        voice_id = request.voice_id or self.voice_identifier
        if voice_id != self.voice_identifier:
            raise VoiceProviderError(
                "invalid_voice_id",
                "The GPT-SoVITS provider only exposes the Akiha reference voice.",
            )
        if self._reference_audio_path is None:
            raise VoiceProviderError(
                "reference_audio_missing",
                "Configure a GPT-SoVITS reference prompt audio file first.",
            )
        return await asyncio.to_thread(self._synthesize_sync, request)

    def _synthesize_sync(self, request: SpeechSynthesisRequest) -> SynthesizedAudio:
        language = _normalize_language(request.language)
        speech_text = " ".join(request.text.split())
        payload: dict[str, Any] = {
            "text": speech_text,
            "text_lang": language,
            "ref_audio_path": str(self._reference_audio_path),
            "prompt_text": self._prompt_text,
            "prompt_lang": self._prompt_language,
            "top_k": self._top_k,
            "top_p": self._top_p,
            "temperature": self._temperature,
            "speed_factor": request.speaking_rate,
            "seed": _stable_seed(speech_text),
            "media_type": "wav",
            "streaming_mode": False,
            "parallel_infer": True,
        }
        try:
            audio_data, media_type = self._transport.request_bytes(
                "POST",
                f"{self._api_url}/tts",
                operation="synthesis",
                payload=payload,
                timeout_seconds=self._timeout_seconds,
            )
        except GptSoVitsTransportError as error:
            raise VoiceProviderError(error.code, str(error)) from error
        except Exception as error:
            raise VoiceProviderError(
                "gpt_sovits_request_failed",
                "GPT-SoVITS synthesis request failed.",
            ) from error

        normalized_media_type = media_type.partition(";")[0].strip().lower()
        is_json = normalized_media_type == "application/json"
        if is_json or audio_data.lstrip().startswith(b"{"):
            raise VoiceProviderError(
                "gpt_sovits_error_response",
                _format_error_response(audio_data),
            )
        if normalized_media_type not in {"audio/wav", "audio/x-wav", ""}:
            raise VoiceProviderError(
                "invalid_audio_response",
                "GPT-SoVITS did not return WAV audio.",
            )
        sample_rate = _read_wav_sample_rate(audio_data)
        return SynthesizedAudio(
            data=audio_data,
            media_type="audio/wav",
            sample_rate_hz=sample_rate,
        )

    async def _request_bytes(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        payload: Mapping[str, Any] | None = None,
    ) -> tuple[bytes, str]:
        try:
            return await asyncio.to_thread(
                self._transport.request_bytes,
                method,
                f"{self._api_url}{path}",
                operation=operation,
                payload=payload,
                timeout_seconds=self._timeout_seconds,
            )
        except GptSoVitsTransportError as error:
            raise VoiceProviderError(error.code, str(error)) from error
        except Exception as error:
            raise VoiceProviderError(
                "gpt_sovits_request_failed",
                f"GPT-SoVITS {operation} failed.",
            ) from error


class UrllibGptSoVitsTransport:
    """Standard-library HTTP transport for the GPT-SoVITS API."""

    def request_bytes(
        self,
        method: str,
        url: str,
        *,
        operation: str,
        payload: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> tuple[bytes, str]:
        encoded = None
        headers = {"Accept": "audio/wav, application/json"}
        if payload is not None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=encoded, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return response.read(), response.headers.get("Content-Type", "")
        except HTTPError as error:
            body = error.read(512)
            detail = body.decode("utf-8", errors="replace").strip()
            raise GptSoVitsTransportError(
                "gpt_sovits_http_error",
                f"GPT-SoVITS returned HTTP {error.code} during {operation}."
                + (f" {detail}" if detail else ""),
            ) from error
        except URLError as error:
            raise GptSoVitsTransportError(
                "gpt_sovits_unreachable",
                "The GPT-SoVITS local API is not reachable.",
            ) from error
        except OSError as error:
            raise GptSoVitsTransportError(
                "gpt_sovits_transport_error",
                f"GPT-SoVITS {operation} could not be completed.",
            ) from error


def _normalize_language(language: str) -> str:
    normalized = language.casefold().replace("_", "-")
    if normalized in {"ja", "ja-jp", "japanese"}:
        return "ja"
    if normalized in {"en", "en-us", "en-gb", "english"}:
        return "en"
    return normalized.split("-", 1)[0]


def _stable_seed(text: str) -> int:
    """Keep repeated text deterministic while avoiding Python hash randomization."""
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "big")


def _read_wav_sample_rate(data: bytes) -> int:
    try:
        with wave.open(io.BytesIO(data), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
    except (EOFError, wave.Error) as error:
        raise VoiceProviderError(
            "invalid_audio_response",
            "GPT-SoVITS returned data that is not a valid WAV file.",
        ) from error
    if sample_rate <= 0:
        raise VoiceProviderError(
            "invalid_audio_response",
            "GPT-SoVITS returned WAV audio with an invalid sample rate.",
        )
    return sample_rate


def _format_error_response(data: bytes) -> str:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "GPT-SoVITS returned an error response instead of audio."
    if isinstance(payload, dict):
        detail = payload.get("message") or payload.get("detail") or payload.get("error")
        if isinstance(detail, str) and detail.strip():
            return f"GPT-SoVITS synthesis failed: {detail.strip()}"
    return "GPT-SoVITS returned an error response instead of audio."
