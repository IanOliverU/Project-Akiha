from __future__ import annotations

import unittest
from collections.abc import Mapping
from typing import Any

from project_akiha.services.ai_provider_discovery import (
    AIProviderDiscoveryError,
    AIProviderDiscoveryRequest,
    discover_ai_provider_models,
)


class AIProviderDiscoveryTest(unittest.TestCase):
    """Verify hosted and local model catalogs without making network calls."""

    def test_discovers_compatible_models_with_bearer_key(self) -> None:
        captured: dict[str, Any] = {}

        def transport(
            url: str,
            headers: Mapping[str, str],
            timeout: float,
        ) -> dict[str, Any]:
            captured.update(url=url, headers=dict(headers), timeout=timeout)
            return {"data": [{"id": "grok-4.5"}, {"id": "grok-4.3"}]}

        result = discover_ai_provider_models(
            AIProviderDiscoveryRequest(
                provider="grok",
                base_url="https://api.x.ai/v1/",
                api_key="secret",
                timeout_seconds=30,
            ),
            transport=transport,
        )

        self.assertEqual(captured["url"], "https://api.x.ai/v1/models")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(captured["timeout"], 15.0)
        self.assertEqual(result.models, ("grok-4.3", "grok-4.5"))

    def test_discovers_installed_ollama_models_without_authorization(self) -> None:
        captured: dict[str, Any] = {}

        def transport(
            url: str,
            headers: Mapping[str, str],
            timeout: float,
        ) -> dict[str, Any]:
            captured.update(url=url, headers=dict(headers), timeout=timeout)
            return {"models": [{"name": "llama3.2:latest"}]}

        result = discover_ai_provider_models(
            AIProviderDiscoveryRequest(
                provider="ollama",
                base_url="http://localhost:11434",
            ),
            transport=transport,
        )

        self.assertEqual(captured["url"], "http://localhost:11434/api/tags")
        self.assertNotIn("Authorization", captured["headers"])
        self.assertEqual(result.models, ("llama3.2:latest",))

    def test_rejects_malformed_catalog(self) -> None:
        with self.assertRaisesRegex(
            AIProviderDiscoveryError,
            "compatible model list",
        ):
            discover_ai_provider_models(
                AIProviderDiscoveryRequest(
                    provider="openai",
                    base_url="https://api.openai.com/v1",
                ),
                transport=lambda _url, _headers, _timeout: {"models": []},
            )


if __name__ == "__main__":
    unittest.main()
