"""Tests for the local VOICEVOX Engine provider."""

from __future__ import annotations

import asyncio
import unittest
from email.message import Message
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError

from project_akiha.providers.voice import (
    SpeechSynthesisRequest,
    UrllibVoiceVoxTransport,
    VoiceProviderError,
    VoiceProviderStatus,
    VoiceVoxProvider,
    VoiceVoxTransportError,
)


class VoiceVoxProviderTest(unittest.TestCase):
    """Verify health, speaker discovery, and two-step synthesis."""

    def test_health_reports_engine_version(self) -> None:
        provider = VoiceVoxProvider(transport=_Transport(version="0.25.0"))

        health = asyncio.run(provider.health())

        self.assertEqual(health.status, VoiceProviderStatus.AVAILABLE)
        self.assertIn("0.25.0", health.detail)

    def test_health_returns_unavailable_on_transport_failure(self) -> None:
        transport = _Transport(
            error=VoiceVoxTransportError(
                "connection_failed",
                "Could not reach VOICEVOX during version check.",
            )
        )
        provider = VoiceVoxProvider(transport=transport)

        health = asyncio.run(provider.health())

        self.assertEqual(health.status, VoiceProviderStatus.UNAVAILABLE)
        self.assertIn("Could not reach", health.detail)

    def test_health_rejects_invalid_version_response(self) -> None:
        provider = VoiceVoxProvider(transport=_Transport(version={"bad": True}))

        health = asyncio.run(provider.health())

        self.assertEqual(health.status, VoiceProviderStatus.UNAVAILABLE)
        self.assertIn("invalid version", health.detail)

    def test_available_voices_flattens_talk_styles(self) -> None:
        transport = _Transport(
            speakers=[
                {
                    "name": "Shikoku Metan",
                    "styles": [
                        {"id": 2, "name": "Normal", "type": "talk"},
                        {"id": 4, "name": "Old compatible style"},
                        {"id": 3000, "name": "Song", "type": "sing"},
                    ],
                }
            ]
        )
        provider = VoiceVoxProvider(transport=transport)

        voices = tuple(asyncio.run(provider.available_voices()))

        self.assertEqual([voice.identifier for voice in voices], ["2", "4"])
        self.assertEqual(voices[0].name, "Shikoku Metan / Normal")
        self.assertEqual(voices[0].language, "ja-JP")

    def test_available_voices_rejects_malformed_response(self) -> None:
        provider = VoiceVoxProvider(transport=_Transport(speakers={"bad": True}))

        with self.assertRaises(VoiceProviderError) as captured:
            asyncio.run(provider.available_voices())

        self.assertEqual(captured.exception.code, "invalid_speakers_response")

    def test_synthesize_applies_speaker_and_speaking_rate(self) -> None:
        transport = _Transport(
            audio_query={
                "speedScale": 1.0,
                "outputSamplingRate": 24_000,
                "accent_phrases": [],
            },
            audio=(b"RIFFvoicevox-wave", "audio/wav"),
        )
        provider = VoiceVoxProvider(
            base_url="http://localhost:50021/",
            timeout_seconds=12,
            transport=transport,
        )

        audio = asyncio.run(
            provider.synthesize(
                SpeechSynthesisRequest(
                    text="Good morning.",
                    voice_id="14",
                    speaking_rate=1.2,
                )
            )
        )

        query_call, synthesis_call = transport.calls
        self.assertEqual(query_call["url"], "http://localhost:50021/audio_query")
        self.assertEqual(
            query_call["query"],
            {"text": "Good morning.", "speaker": "14"},
        )
        self.assertEqual(synthesis_call["url"], "http://localhost:50021/synthesis")
        self.assertEqual(synthesis_call["query"], {"speaker": "14"})
        self.assertEqual(synthesis_call["payload"]["speedScale"], 1.2)
        self.assertEqual(query_call["timeout_seconds"], 12)
        self.assertEqual(audio.data, b"RIFFvoicevox-wave")
        self.assertEqual(audio.sample_rate_hz, 24_000)

    def test_synthesize_rejects_invalid_voice_id_before_http(self) -> None:
        transport = _Transport()
        provider = VoiceVoxProvider(transport=transport)

        with self.assertRaises(VoiceProviderError) as captured:
            asyncio.run(
                provider.synthesize(
                    SpeechSynthesisRequest(text="Test.", voice_id="not-a-number")
                )
            )

        self.assertEqual(captured.exception.code, "invalid_voice_id")
        self.assertEqual(transport.calls, [])

    def test_synthesize_rejects_non_wav_response(self) -> None:
        provider = VoiceVoxProvider(
            transport=_Transport(audio=(b'{"error":true}', "application/json"))
        )

        with self.assertRaises(VoiceProviderError) as captured:
            asyncio.run(
                provider.synthesize(SpeechSynthesisRequest(text="Test.", voice_id="0"))
            )

        self.assertEqual(captured.exception.code, "invalid_audio_response")

    def test_unexpected_transport_error_does_not_echo_spoken_text(self) -> None:
        secret = "private spoken response"
        provider = VoiceVoxProvider(
            transport=_Transport(error=RuntimeError(f"failed with {secret}"))
        )

        with self.assertRaises(VoiceProviderError) as captured:
            asyncio.run(
                provider.synthesize(SpeechSynthesisRequest(text=secret, voice_id="0"))
            )

        self.assertEqual(captured.exception.code, "voicevox_request_failed")
        self.assertNotIn(secret, str(captured.exception))


class UrllibVoiceVoxTransportTest(unittest.TestCase):
    """Verify default HTTP errors remain privacy-safe."""

    def test_http_error_does_not_echo_query_text(self) -> None:
        secret = "private spoken response"
        error = HTTPError(
            f"http://localhost/audio_query?text={secret}",
            422,
            "Unprocessable",
            Message(),
            None,
        )
        transport = UrllibVoiceVoxTransport()

        with patch(
            "project_akiha.providers.voice.voicevox.urlopen",
            side_effect=error,
        ):
            with self.assertRaises(VoiceVoxTransportError) as captured:
                transport.request_json(
                    "POST",
                    "http://localhost/audio_query",
                    operation="audio query",
                    query={"text": secret, "speaker": "0"},
                    payload=None,
                    timeout_seconds=5,
                )

        self.assertEqual(captured.exception.code, "http_error")
        self.assertNotIn(secret, str(captured.exception))


class _Transport:
    def __init__(
        self,
        *,
        version: Any = "0.25.0",
        speakers: Any = None,
        audio_query: Any = None,
        audio: tuple[bytes, str] = (b"RIFFwave", "audio/wav"),
        error: Exception | None = None,
    ) -> None:
        self.version = version
        self.speakers = (
            [{"name": "Speaker", "styles": [{"id": 0, "name": "Normal"}]}]
            if speakers is None
            else speakers
        )
        self.audio_query = (
            {"speedScale": 1.0, "outputSamplingRate": 24_000}
            if audio_query is None
            else audio_query
        )
        self.audio = audio
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def request_json(
        self,
        method: str,
        url: str,
        *,
        operation: str,
        query: object,
        payload: object,
        timeout_seconds: float,
    ) -> Any:
        if self.error is not None:
            raise self.error
        self.calls.append(
            {
                "method": method,
                "url": url,
                "operation": operation,
                "query": query,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        if url.endswith("/version"):
            return self.version
        if url.endswith("/speakers"):
            return self.speakers
        if isinstance(self.audio_query, dict):
            return dict(self.audio_query)
        return self.audio_query

    def request_bytes(
        self,
        method: str,
        url: str,
        *,
        operation: str,
        query: object,
        payload: object,
        timeout_seconds: float,
    ) -> tuple[bytes, str]:
        if self.error is not None:
            raise self.error
        self.calls.append(
            {
                "method": method,
                "url": url,
                "operation": operation,
                "query": query,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.audio


if __name__ == "__main__":
    unittest.main()
