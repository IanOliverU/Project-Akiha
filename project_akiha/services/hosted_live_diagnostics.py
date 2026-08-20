"""Privacy-safe local readiness checks for hosted live conversation."""

from __future__ import annotations

from dataclasses import dataclass

from project_akiha.config import PrivacyConfig, VoiceConfig
from project_akiha.providers.live.google_sdk import probe_google_genai_sdk
from project_akiha.services.credential_store import (
    CredentialStore,
    CredentialStoreError,
)
from project_akiha.services.privacy_notice import hosted_live_privacy_notice_required


@dataclass(frozen=True, slots=True)
class HostedLiveDiagnosticsSnapshot:
    """Non-sensitive hosted-live setup state safe to display or log."""

    sdk_available: bool
    sdk_detail: str
    api_key_available: bool
    privacy_notice_current: bool
    selected: bool
    model: str
    voice_name: str
    max_duration_seconds: int
    processing_location: str = "Google Gemini API (off device)"
    context_compression_enabled: bool = True
    session_resumption_enabled: bool = True

    @property
    def ready(self) -> bool:
        """Return whether local prerequisites permit a hosted session attempt."""
        return (
            self.sdk_available
            and self.api_key_available
            and self.privacy_notice_current
        )


def build_hosted_live_diagnostics(
    voice: VoiceConfig,
    privacy: PrivacyConfig,
    credential_store: CredentialStore | None,
) -> HostedLiveDiagnosticsSnapshot:
    """Inspect local setup without opening a provider connection or microphone."""
    sdk = probe_google_genai_sdk()

    api_key_available = False
    if credential_store is not None:
        try:
            api_key_available = bool(credential_store.get_secret("gemini"))
        except CredentialStoreError:
            api_key_available = False

    return HostedLiveDiagnosticsSnapshot(
        sdk_available=sdk.available,
        sdk_detail=sdk.detail,
        api_key_available=api_key_available,
        privacy_notice_current=not hosted_live_privacy_notice_required(privacy),
        selected=voice.session_provider == "gemini_live",
        model=voice.hosted_live_model,
        voice_name=voice.hosted_live_voice_name,
        max_duration_seconds=voice.hosted_live_max_duration_seconds,
    )
