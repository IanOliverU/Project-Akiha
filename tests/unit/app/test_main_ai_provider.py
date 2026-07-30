"""Tests for main application AI provider composition."""

from __future__ import annotations

import logging
import os
import unittest
from unittest.mock import patch

from project_akiha.app.main import _build_ai_provider
from project_akiha.config import AIConfig
from project_akiha.providers.ai import (
    MockAIProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    UnavailableAIProvider,
)


class _CredentialStore:
    def __init__(self, secret: str | None = None) -> None:
        self.secret = secret
        self.requested_provider = ""

    def get_secret(self, provider: str) -> str | None:
        self.requested_provider = provider
        return self.secret

    def set_secret(self, provider: str, secret: str) -> None:
        del provider, secret

    def delete_secret(self, provider: str) -> None:
        del provider


class MainAIProviderTest(unittest.TestCase):
    """Verify provider selection keeps local and hosted paths independent."""

    def setUp(self) -> None:
        self.logger = logging.getLogger("test.main.ai")

    def test_builds_mock_and_ollama_without_credentials(self) -> None:
        credentials = _CredentialStore()

        mock = _build_ai_provider(AIConfig(), self.logger, credentials)
        ollama = _build_ai_provider(
            AIConfig(provider="ollama"),
            self.logger,
            credentials,
        )

        self.assertIsInstance(mock, MockAIProvider)
        self.assertIsInstance(ollama, OllamaProvider)
        self.assertEqual(credentials.requested_provider, "")

    def test_builds_hosted_provider_with_saved_key(self) -> None:
        credentials = _CredentialStore("saved-key")

        provider = _build_ai_provider(
            AIConfig(provider="gemini"),
            self.logger,
            credentials,
        )

        self.assertIsInstance(provider, OpenAICompatibleProvider)
        self.assertEqual(credentials.requested_provider, "gemini")

    def test_missing_required_key_builds_unavailable_provider(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            provider = _build_ai_provider(
                AIConfig(provider="gemini"),
                self.logger,
                _CredentialStore(),
            )

        self.assertIsInstance(provider, UnavailableAIProvider)

    def test_environment_key_is_supported(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "environment-key"}):
            provider = _build_ai_provider(
                AIConfig(provider="gemini"),
                self.logger,
                _CredentialStore(),
            )

        self.assertIsInstance(provider, OpenAICompatibleProvider)

    def test_grok_environment_key_is_supported(self) -> None:
        with patch.dict(os.environ, {"XAI_API_KEY": "environment-key"}, clear=True):
            provider = _build_ai_provider(
                AIConfig(
                    provider="grok",
                    hosted_base_url="https://api.x.ai/v1",
                    hosted_model="grok-4.5",
                ),
                self.logger,
                _CredentialStore(),
            )

        self.assertIsInstance(provider, OpenAICompatibleProvider)

    def test_keyless_custom_compatible_endpoint_is_supported(self) -> None:
        provider = _build_ai_provider(
            AIConfig(provider="openai-compatible"),
            self.logger,
            _CredentialStore(),
        )

        self.assertIsInstance(provider, OpenAICompatibleProvider)


if __name__ == "__main__":
    unittest.main()
