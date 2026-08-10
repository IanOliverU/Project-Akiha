"""Tests for privacy-safe Gemini Live readiness checks."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from project_akiha.config import PrivacyConfig, VoiceConfig
from project_akiha.services.hosted_live_diagnostics import (
    build_hosted_live_diagnostics,
)
from project_akiha.services.privacy_notice import (
    acknowledge_current_hosted_live_privacy_notice,
)


class _Credentials:
    def __init__(self, key: str | None) -> None:
        self.key = key

    def get_secret(self, provider: str) -> str | None:
        return self.key if provider == "gemini" else None


class HostedLiveDiagnosticsTest(unittest.TestCase):
    """Verify readiness checks expose state without provider activity."""

    @patch("project_akiha.services.hosted_live_diagnostics.find_spec")
    def test_ready_requires_sdk_key_and_current_notice(self, find_spec) -> None:
        find_spec.return_value = object()
        privacy = acknowledge_current_hosted_live_privacy_notice(PrivacyConfig())

        snapshot = build_hosted_live_diagnostics(
            VoiceConfig(session_provider="gemini_live"),
            privacy,
            _Credentials("secret"),
        )

        self.assertTrue(snapshot.ready)
        self.assertTrue(snapshot.selected)
        self.assertEqual(snapshot.processing_location, "Google Gemini API (off device)")
        self.assertTrue(snapshot.context_compression_enabled)
        self.assertTrue(snapshot.session_resumption_enabled)

    @patch("project_akiha.services.hosted_live_diagnostics.find_spec")
    def test_missing_prerequisites_are_reported_without_secrets(
        self, find_spec
    ) -> None:
        find_spec.return_value = None

        snapshot = build_hosted_live_diagnostics(
            VoiceConfig(),
            PrivacyConfig(),
            _Credentials(None),
        )

        self.assertFalse(snapshot.ready)
        self.assertFalse(snapshot.sdk_available)
        self.assertFalse(snapshot.api_key_available)
        self.assertFalse(snapshot.privacy_notice_current)
        self.assertNotIn("secret", repr(snapshot).casefold())


if __name__ == "__main__":
    unittest.main()
