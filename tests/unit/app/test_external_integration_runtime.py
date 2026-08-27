"""Tests for optional external-provider lifecycle isolation."""

from __future__ import annotations

import logging
import unittest
from unittest.mock import Mock

from project_akiha.app.external_integration_runtime import ExternalIntegrationRuntime
from project_akiha.config import ExternalIntegrationsConfig
from project_akiha.core.integrations import ExternalService


class ExternalIntegrationRuntimeTest(unittest.TestCase):
    def test_start_refresh_reconfigure_and_stop(self) -> None:
        gmail = _Provider("gmail")
        discord = _Provider("discord")
        runtime = ExternalIntegrationRuntime(gmail, discord, lambda _event: None)

        runtime.start()
        runtime.refresh(ExternalService.GMAIL)
        runtime.apply_config(ExternalIntegrationsConfig())
        runtime.stop()

        self.assertEqual(gmail.start_calls, 2)
        self.assertEqual(discord.start_calls, 2)
        self.assertEqual(gmail.refresh_calls, 1)
        self.assertEqual(gmail.apply_calls, 1)
        self.assertEqual(discord.apply_calls, 1)
        self.assertEqual(gmail.stop_calls, 2)
        self.assertEqual(discord.stop_calls, 2)

    def test_one_shutdown_failure_does_not_block_other_provider(self) -> None:
        gmail = _Provider("gmail", fail_stop=True)
        discord = _Provider("discord")
        logger = Mock(spec=logging.Logger)
        runtime = ExternalIntegrationRuntime(
            gmail,
            discord,
            lambda _event: None,
            logger=logger,
        )

        runtime.start()
        runtime.stop()

        self.assertEqual(discord.stop_calls, 1)
        logger.exception.assert_called_once()


class _Provider:
    def __init__(self, name: str, *, fail_stop: bool = False) -> None:
        self.name = name
        self.health_status = "disabled"
        self.fail_stop = fail_stop
        self.start_calls = 0
        self.stop_calls = 0
        self.refresh_calls = 0
        self.apply_calls = 0

    def start(self, _callback) -> None:
        self.start_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1
        if self.fail_stop:
            raise RuntimeError("provider stop failed")

    def refresh(self) -> None:
        self.refresh_calls += 1

    def apply_config(self, _config) -> None:
        self.apply_calls += 1


if __name__ == "__main__":
    unittest.main()
