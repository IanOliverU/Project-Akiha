"""Tests for the optional-runtime smoke report boundary."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from project_akiha.config import AppConfig
from project_akiha.providers.live.google_sdk import GoogleGenAISdkProbe
from project_akiha.services.provider_runtime_smoke import (
    ProviderRuntimeCheck,
    run_provider_runtime_smoke,
)


class ProviderRuntimeSmokeTest(unittest.IsolatedAsyncioTestCase):
    @patch(
        "project_akiha.services.provider_runtime_smoke._check_gpt_sovits",
        new_callable=AsyncMock,
    )
    @patch(
        "project_akiha.services.provider_runtime_smoke._check_gemini_client",
        new_callable=AsyncMock,
    )
    @patch("project_akiha.services.provider_runtime_smoke.probe_google_genai_sdk")
    async def test_report_combines_real_runtime_boundaries_without_secrets(
        self,
        probe_sdk,
        check_gemini,
        check_gpt,
    ) -> None:
        probe_sdk.return_value = GoogleGenAISdkProbe(True, "SDK ready.")
        check_gemini.return_value = ProviderRuntimeCheck(
            "gemini_live_connection",
            "passed",
            "Connected.",
        )
        check_gpt.return_value = (
            ProviderRuntimeCheck("gpt_sovits_health", "passed", "Healthy."),
            ProviderRuntimeCheck("gpt_sovits_synthesis", "passed", "Audio ready."),
        )

        report = await run_provider_runtime_smoke(
            AppConfig(),
            project_root=None,  # type: ignore[arg-type]
            credential_store=object(),  # type: ignore[arg-type]
            connect_gemini=True,
        )

        self.assertTrue(report.passed)
        self.assertEqual(len(report.checks), 4)
        self.assertNotIn("credential", report.to_json().casefold())


if __name__ == "__main__":
    unittest.main()
