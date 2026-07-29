"""Local VOICEVOX Engine speech synthesis provider."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from project_akiha.providers.voice.base import (
    SpeechSynthesisRequest,
    SynthesizedAudio,
    VoiceOption,
    VoiceProviderError,
    VoiceProviderHealth,
    VoiceProviderStatus,
)

JSONValue = Any


class VoiceVoxTransportError(RuntimeError):
    """A privacy-safe local HTTP transport failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code.strip() or "voicevox_transport_error"


class VoiceVoxTransport(Protocol):
    """Synchronous HTTP transport run outside the asyncio event loop."""

    def request_json(
        self,
        method: str,
        url: str,
        *,
        operation: str,
        query: Mapping[str, str] | None,
        payload: Mapping[str, JSONValue] | None,
        timeout_seconds: float,
    ) -> JSONValue:
        """Return a decoded JSON response."""

    def request_bytes(
        self,
        method: str,
        url: str,
        *,
        operation: str,
        query: Mapping[str, str] | None,
        payload: Mapping[str, JSONValue] | None,
        timeout_seconds: float,
    ) -> tuple[bytes, str]:
        """Return response bytes and media type."""


class VoiceVoxProvider:
    """Use a running local VOICEVOX Engine through its HTTP API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:50021",
        timeout_seconds: float = 30.0,
        transport: VoiceVoxTransport | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("VOICEVOX timeout must be greater than zero.")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport or UrllibVoiceVoxTransport()

    async def health(self) -> VoiceProviderHealth:
        """Return whether the configured VOICEVOX Engine is reachable."""
        try:
            version = await self._request_json(
                "GET",
                "/version",
                operation="version check",
            )
        except VoiceProviderError as error:
            return VoiceProviderHealth(VoiceProviderStatus.UNAVAILABLE, str(error))

        if not isinstance(version, str) or not version.strip():
            return VoiceProviderHealth(
                VoiceProviderStatus.UNAVAILABLE,
                "VOICEVOX returned an invalid version response.",
            )
        return VoiceProviderHealth(
            VoiceProviderStatus.AVAILABLE,
            f"VOICEVOX Engine {version.strip()} is available.",
        )

    async def available_voices(self) -> Sequence[VoiceOption]:
        """Return talk-capable speaker styles exposed by the engine."""
        payload = await self._request_json(
            "GET",
            "/speakers",
            operation="speaker discovery",
        )
        return _parse_voice_options(payload)

    async def synthesize(
        self,
        request: SpeechSynthesisRequest,
    ) -> SynthesizedAudio:
        """Create an audio query, apply speaking rate, and return WAV bytes."""
        speaker_id = _parse_speaker_id(request.voice_id)
        query = await self._request_json(
            "POST",
            "/audio_query",
            operation="audio query",
            query={"text": request.text, "speaker": str(speaker_id)},
        )
        if not isinstance(query, dict):
            raise VoiceProviderError(
                "invalid_audio_query",
                "VOICEVOX returned an invalid audio query.",
            )

        query["speedScale"] = request.speaking_rate
        audio_data, media_type = await self._request_bytes(
            "POST",
            "/synthesis",
            operation="synthesis",
            query={"speaker": str(speaker_id)},
            payload=query,
        )
        normalized_media_type = media_type.partition(";")[0].strip().lower()
        if normalized_media_type not in {"audio/wav", "audio/x-wav"}:
            raise VoiceProviderError(
                "invalid_audio_response",
                "VOICEVOX synthesis did not return WAV audio.",
            )
        if not audio_data:
            raise VoiceProviderError(
                "empty_audio_response",
                "VOICEVOX synthesis returned empty audio.",
            )

        sample_rate = query.get("outputSamplingRate")
        if not isinstance(sample_rate, int) or isinstance(sample_rate, bool):
            sample_rate = None
        elif sample_rate <= 0:
            sample_rate = None
        return SynthesizedAudio(
            data=audio_data,
            media_type="audio/wav",
            sample_rate_hz=sample_rate,
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        query: Mapping[str, str] | None = None,
        payload: Mapping[str, JSONValue] | None = None,
    ) -> JSONValue:
        try:
            return await asyncio.to_thread(
                self._transport.request_json,
                method,
                f"{self._base_url}{path}",
                operation=operation,
                query=query,
                payload=payload,
                timeout_seconds=self._timeout_seconds,
            )
        except VoiceVoxTransportError as error:
            raise VoiceProviderError(error.code, str(error)) from error
        except Exception as error:
            raise VoiceProviderError(
                "voicevox_request_failed",
                f"VOICEVOX {operation} failed.",
            ) from error

    async def _request_bytes(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        query: Mapping[str, str] | None = None,
        payload: Mapping[str, JSONValue] | None = None,
    ) -> tuple[bytes, str]:
        try:
            return await asyncio.to_thread(
                self._transport.request_bytes,
                method,
                f"{self._base_url}{path}",
                operation=operation,
                query=query,
                payload=payload,
                timeout_seconds=self._timeout_seconds,
            )
        except VoiceVoxTransportError as error:
            raise VoiceProviderError(error.code, str(error)) from error
        except Exception as error:
            raise VoiceProviderError(
                "voicevox_request_failed",
                f"VOICEVOX {operation} failed.",
            ) from error


class UrllibVoiceVoxTransport:
    """VOICEVOX transport implemented with the Python standard library."""

    def request_json(
        self,
        method: str,
        url: str,
        *,
        operation: str,
        query: Mapping[str, str] | None,
        payload: Mapping[str, JSONValue] | None,
        timeout_seconds: float,
    ) -> JSONValue:
        """Return decoded JSON without exposing request query text in errors."""
        data, _ = self._request(
            method,
            url,
            operation=operation,
            query=query,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise VoiceVoxTransportError(
                "invalid_response",
                f"VOICEVOX returned invalid JSON for {operation}.",
            ) from error

    def request_bytes(
        self,
        method: str,
        url: str,
        *,
        operation: str,
        query: Mapping[str, str] | None,
        payload: Mapping[str, JSONValue] | None,
        timeout_seconds: float,
    ) -> tuple[bytes, str]:
        """Return response bytes and content type."""
        return self._request(
            method,
            url,
            operation=operation,
            query=query,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        operation: str,
        query: Mapping[str, str] | None,
        payload: Mapping[str, JSONValue] | None,
        timeout_seconds: float,
    ) -> tuple[bytes, str]:
        request_url = _append_query(url, query)
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        if method.upper() == "POST" and data is None:
            data = b""
        headers = {"Accept": "application/json, audio/wav"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = Request(
            request_url,
            data=data,
            headers=headers,
            method=method.upper(),
        )

        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                content_type = response.headers.get_content_type()
                return response.read(), content_type
        except HTTPError as error:
            raise VoiceVoxTransportError(
                "http_error",
                f"VOICEVOX returned HTTP {error.code} for {operation}.",
            ) from error
        except (OSError, TimeoutError, URLError) as error:
            raise VoiceVoxTransportError(
                "connection_failed",
                f"Could not reach VOICEVOX during {operation}.",
            ) from error


def _append_query(url: str, query: Mapping[str, str] | None) -> str:
    if not query:
        return url
    return f"{url}?{urlencode(query)}"


def _parse_speaker_id(voice_id: str | None) -> int:
    if voice_id is None:
        raise VoiceProviderError(
            "voice_not_selected",
            "A VOICEVOX speaker style must be selected.",
        )
    try:
        speaker_id = int(voice_id.strip())
    except (TypeError, ValueError) as error:
        raise VoiceProviderError(
            "invalid_voice_id",
            "The configured VOICEVOX speaker style is invalid.",
        ) from error
    if speaker_id < 0:
        raise VoiceProviderError(
            "invalid_voice_id",
            "The configured VOICEVOX speaker style is invalid.",
        )
    return speaker_id


def _parse_voice_options(payload: JSONValue) -> tuple[VoiceOption, ...]:
    if not isinstance(payload, list):
        raise VoiceProviderError(
            "invalid_speakers_response",
            "VOICEVOX returned an invalid speaker list.",
        )

    options: list[VoiceOption] = []
    for speaker in payload:
        if not isinstance(speaker, dict):
            raise VoiceProviderError(
                "invalid_speakers_response",
                "VOICEVOX returned an invalid speaker entry.",
            )
        speaker_name = speaker.get("name")
        styles = speaker.get("styles")
        if not isinstance(speaker_name, str) or not speaker_name.strip():
            raise VoiceProviderError(
                "invalid_speakers_response",
                "VOICEVOX returned a speaker without a name.",
            )
        if not isinstance(styles, list):
            raise VoiceProviderError(
                "invalid_speakers_response",
                "VOICEVOX returned invalid speaker styles.",
            )
        for style in styles:
            if not isinstance(style, dict):
                raise VoiceProviderError(
                    "invalid_speakers_response",
                    "VOICEVOX returned an invalid speaker style.",
                )
            style_type = style.get("type")
            if style_type is not None and not isinstance(style_type, str):
                raise VoiceProviderError(
                    "invalid_speakers_response",
                    "VOICEVOX returned an invalid speaker style type.",
                )
            if style_type not in {None, "talk"}:
                continue
            style_id = style.get("id")
            style_name = style.get("name")
            if (
                not isinstance(style_id, int)
                or isinstance(style_id, bool)
                or style_id < 0
                or not isinstance(style_name, str)
                or not style_name.strip()
            ):
                raise VoiceProviderError(
                    "invalid_speakers_response",
                    "VOICEVOX returned an invalid talk style.",
                )
            options.append(
                VoiceOption(
                    identifier=str(style_id),
                    name=f"{speaker_name.strip()} / {style_name.strip()}",
                    language="ja-JP",
                )
            )

    return tuple(options)
