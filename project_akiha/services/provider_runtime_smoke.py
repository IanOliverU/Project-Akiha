"""Real, privacy-safe smoke checks for optional packaged runtimes."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from project_akiha.config import AppConfig
from project_akiha.core.voice_session import LiveResponseModality, LiveSessionError
from project_akiha.providers.live import (
    GeminiLiveTransportConfig,
    GoogleGenAILiveTransport,
)
from project_akiha.providers.live.google_sdk import (
    load_google_genai_sdk,
    probe_google_genai_sdk,
)
from project_akiha.providers.voice import (
    GptSoVitsProvider,
    SpeechSynthesisRequest,
    VoiceProviderError,
    VoiceProviderStatus,
)
from project_akiha.services.credential_store import (
    CredentialStore,
    CredentialStoreError,
)
from project_akiha.services.gpt_sovits_engine_manager import GptSoVitsEngineManager
from project_akiha.services.gpt_sovits_reference import resolve_gpt_sovits_prompt


@dataclass(frozen=True, slots=True)
class ProviderRuntimeCheck:
    """One non-sensitive runtime verification result."""

    name: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class ProviderRuntimeSmokeReport:
    """Machine-readable report written by source or packaged Akiha."""

    schema_version: int
    passed: bool
    checks: tuple[ProviderRuntimeCheck, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


async def run_provider_runtime_smoke(
    config: AppConfig,
    project_root: Path,
    credential_store: CredentialStore,
    *,
    connect_gemini: bool,
) -> ProviderRuntimeSmokeReport:
    """Exercise real SDK loading, optional Gemini connection, and local TTS."""
    checks: list[ProviderRuntimeCheck] = []
    sdk = probe_google_genai_sdk()
    checks.append(
        ProviderRuntimeCheck(
            "gemini_sdk_import",
            "passed" if sdk.available else "failed",
            sdk.detail,
        )
    )

    if sdk.available:
        checks.append(
            await _check_gemini_client(
                config,
                credential_store,
                connect=connect_gemini,
            )
        )
    else:
        checks.append(
            ProviderRuntimeCheck(
                "gemini_live_connection",
                "failed",
                "Gemini Live was not attempted because the SDK import failed.",
            )
        )

    checks.extend(await _check_gpt_sovits(config, project_root))
    passed = all(check.status in {"passed", "skipped"} for check in checks)
    return ProviderRuntimeSmokeReport(1, passed, tuple(checks))


async def _check_gemini_client(
    config: AppConfig,
    credential_store: CredentialStore,
    *,
    connect: bool,
) -> ProviderRuntimeCheck:
    if not connect:
        try:
            genai, _ = load_google_genai_sdk()
            genai.Client(api_key="runtime-smoke-placeholder")
        except Exception as error:
            return ProviderRuntimeCheck(
                "gemini_live_connection",
                "failed",
                f"Gemini SDK client initialization failed ({type(error).__name__}).",
            )
        return ProviderRuntimeCheck(
            "gemini_live_connection",
            "skipped",
            "Gemini SDK client construction passed; network connection was skipped.",
        )

    try:
        api_key = credential_store.get_secret("gemini")
    except CredentialStoreError:
        return ProviderRuntimeCheck(
            "gemini_live_connection",
            "failed",
            "The saved Gemini credential could not be decrypted.",
        )
    if not api_key:
        return ProviderRuntimeCheck(
            "gemini_live_connection",
            "failed",
            "No saved Gemini credential is available for the smoke check.",
        )

    transport = GoogleGenAILiveTransport(api_key)
    try:
        await transport.connect(
            GeminiLiveTransportConfig(
                model_name=config.voice.hosted_live_model,
                response_modality=LiveResponseModality.AUDIO,
                input_audio_transcription=True,
                output_audio_transcription=True,
                context_window_compression=True,
                session_resumption=True,
                voice_name=config.voice.hosted_live_voice_name,
            )
        )
    except LiveSessionError as error:
        return ProviderRuntimeCheck(
            "gemini_live_connection",
            "failed",
            f"Gemini Live connection failed ({error.code.value}).",
        )
    except Exception as error:
        return ProviderRuntimeCheck(
            "gemini_live_connection",
            "failed",
            f"Gemini SDK client initialization failed ({type(error).__name__}).",
        )
    finally:
        await transport.close()
    return ProviderRuntimeCheck(
        "gemini_live_connection",
        "passed",
        "Gemini Live opened and closed a provider session successfully.",
    )


async def _check_gpt_sovits(
    config: AppConfig,
    project_root: Path,
) -> tuple[ProviderRuntimeCheck, ...]:
    voice = config.voice
    if voice.output_provider != "gpt-sovits":
        skipped = ProviderRuntimeCheck(
            "gpt_sovits_health",
            "skipped",
            "GPT-SoVITS is not the selected speech output provider.",
        )
        return (skipped,)

    manager = GptSoVitsEngineManager(project_root)
    manager.apply_config(voice)
    try:
        if voice.output_engine_auto_start:
            ready = await asyncio.to_thread(
                manager.wait_until_ready,
                voice.output_base_url,
                timeout_seconds=max(60.0, float(voice.request_timeout_seconds)),
            )
            if not ready:
                return (
                    ProviderRuntimeCheck(
                        "gpt_sovits_health",
                        "failed",
                        "The managed GPT-SoVITS API did not become ready in time.",
                    ),
                )

        reference_audio, prompt_text = resolve_gpt_sovits_prompt(
            project_root,
            voice.output_reference_dir,
            voice.output_prompt_text,
        )
        provider = GptSoVitsProvider(
            api_url=voice.output_base_url,
            reference_audio_path=reference_audio,
            prompt_text=prompt_text,
            timeout_seconds=float(voice.request_timeout_seconds),
        )
        health = await provider.health()
        if health.status != VoiceProviderStatus.AVAILABLE:
            return (
                ProviderRuntimeCheck(
                    "gpt_sovits_health",
                    "failed",
                    health.detail,
                ),
            )
        health_check = ProviderRuntimeCheck(
            "gpt_sovits_health",
            "passed",
            "GPT-SoVITS and its external reference audio are available.",
        )
        try:
            audio = await provider.synthesize(
                SpeechSynthesisRequest(
                    text="こんにちは。",
                    voice_id=voice.output_voice_id,
                    language="ja-JP",
                    speaking_rate=voice.speaking_rate,
                )
            )
        except VoiceProviderError as error:
            return (
                health_check,
                ProviderRuntimeCheck(
                    "gpt_sovits_synthesis",
                    "failed",
                    f"GPT-SoVITS synthesis failed ({error.code}).",
                ),
            )
        synthesis = ProviderRuntimeCheck(
            "gpt_sovits_synthesis",
            "passed" if audio.data else "failed",
            (
                "GPT-SoVITS returned valid in-memory WAV audio."
                if audio.data
                else "GPT-SoVITS returned empty audio."
            ),
        )
        return health_check, synthesis
    finally:
        manager.shutdown()


def write_provider_runtime_smoke_report(
    report: ProviderRuntimeSmokeReport,
    destination: Path,
) -> None:
    """Atomically persist a report without credentials, transcripts, or audio."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(report.to_json() + "\n", encoding="utf-8")
    temporary.replace(destination)
