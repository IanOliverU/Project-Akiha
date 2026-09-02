"""Tests for bounded unified provider health diagnostics."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from project_akiha.services.provider_health_registry import (
    ProviderHealthRegistry,
    ProviderHealthState,
    render_provider_health_summary,
)


class ProviderHealthRegistryTest(unittest.TestCase):
    def test_records_and_renders_privacy_safe_health(self) -> None:
        registry = ProviderHealthRegistry()
        registry.update(
            "gpt_sovits",
            ProviderHealthState.HEALTHY,
            "endpoint_ready",
            checked_at=datetime(2026, 9, 2, tzinfo=UTC),
            startup_duration_ms=1250,
        )

        summary = render_provider_health_summary(registry.snapshot())

        self.assertIn("Gpt Sovits: healthy", summary)
        self.assertIn("1250 ms", summary)

    def test_rejects_unbounded_detail_instead_of_logging_it(self) -> None:
        with self.assertRaises(ValueError):
            ProviderHealthRegistry().update(
                "gmail",
                ProviderHealthState.UNAVAILABLE,
                "token=secret value",
            )


if __name__ == "__main__":
    unittest.main()
