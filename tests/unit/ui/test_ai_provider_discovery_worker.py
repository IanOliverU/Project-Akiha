from __future__ import annotations

import unittest

from project_akiha.services.ai_provider_discovery import (
    AIProviderDiscoveryRequest,
    AIProviderDiscoveryResult,
)
from project_akiha.ui.ai_provider_discovery_worker import (
    AIProviderDiscoveryThread,
)


class AIProviderDiscoveryThreadTest(unittest.TestCase):
    """Verify worker success and privacy-safe failure signaling."""

    def test_run_emits_discovered_models(self) -> None:
        request = AIProviderDiscoveryRequest(
            provider="grok",
            base_url="https://api.x.ai/v1",
        )
        expected = AIProviderDiscoveryResult("grok", ("grok-4.5",))
        thread = AIProviderDiscoveryThread(
            request,
            service=lambda _request: expected,
        )
        emitted: list[object] = []
        thread.models_ready.connect(emitted.append)

        thread.run()

        self.assertEqual(emitted, [expected])

    def test_run_emits_failure_without_request_details(self) -> None:
        request = AIProviderDiscoveryRequest(
            provider="grok",
            base_url="https://api.x.ai/v1",
            api_key="private-key",
        )

        def fail(_request: AIProviderDiscoveryRequest) -> AIProviderDiscoveryResult:
            raise RuntimeError("Connection failed.")

        thread = AIProviderDiscoveryThread(request, service=fail)
        emitted: list[str] = []
        thread.discovery_failed.connect(emitted.append)

        thread.run()

        self.assertEqual(emitted, ["Connection failed."])
        self.assertNotIn("private-key", emitted[0])


if __name__ == "__main__":
    unittest.main()
