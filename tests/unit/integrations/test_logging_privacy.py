"""Unexpected provider failures must not persist transport-owned details."""

import logging
import unittest
from unittest.mock import Mock, patch

from project_akiha.config import DiscordIntegrationConfig, GmailIntegrationConfig
from project_akiha.integrations.discord.gateway import DiscordGatewayProvider
from project_akiha.integrations.gmail.provider import GmailIntegrationProvider


class IntegrationLoggingPrivacyTest(unittest.TestCase):
    def test_gmail_unexpected_failure_is_bounded_and_next_poll_recovers(self):
        sentinel = "PRIVATE_GMAIL_TOKEN_SUBJECT_PATH_" * 1000
        health = []
        provider = GmailIntegrationProvider(
            GmailIntegrationConfig(
                enabled=True, client_id="synthetic.apps.googleusercontent.com"
            ),
            Mock(),
            Mock(),
            Mock(),
            on_health=lambda _service, status, _at: health.append(status),
        )
        with patch.object(provider, "_poll_once", side_effect=RuntimeError(sentinel)):
            with self.assertLogs(provider._logger, logging.WARNING) as captured:
                provider._poll_safely()
        self._assert_sanitized(captured, sentinel)
        self.assertEqual(health, ["connecting", "provider_unavailable"])
        with patch.object(provider, "_poll_once"):
            provider._poll_safely()
        self.assertEqual(health[-2:], ["connecting", "available"])

    def test_discord_unexpected_failure_reconnects_with_existing_backoff(self):
        sentinel = "PRIVATE_DISCORD_TOKEN_FRAME_PATH_" * 1000
        health = []
        failed = Mock()
        failed.run_forever.side_effect = RuntimeError(sentinel)
        recovered = Mock()
        factory = Mock(side_effect=[failed, recovered])
        provider = DiscordGatewayProvider(
            DiscordIntegrationConfig(enabled=True),
            Mock(),
            websocket_factory=factory,
            on_health=lambda _service, status, _at: health.append(status),
        )
        recovered.run_forever.side_effect = lambda **_kwargs: provider._stop_event.set()
        with patch.object(provider._stop_event, "wait", return_value=False) as wait:
            with patch(
                "project_akiha.integrations.discord.gateway.random.random",
                return_value=0.25,
            ):
                with self.assertLogs(provider._logger, logging.WARNING) as captured:
                    provider._run()
        self._assert_sanitized(captured, sentinel)
        self.assertEqual(factory.call_count, 2)
        wait.assert_called_once_with(1.25)
        self.assertEqual(health, ["connecting", "provider_unavailable", "connecting"])
        self.assertIsNone(provider._socket)

    def _assert_sanitized(self, captured, sentinel):
        self.assertEqual(len(captured.records), 1)
        record = captured.records[0]
        self.assertIsNone(record.exc_info)
        self.assertIsNone(record.stack_info)
        self.assertIsNone(record.exc_text)
        self.assertNotIn(sentinel[:32], "\n".join(captured.output))
        self.assertLess(len("\n".join(captured.output)), 200)
        self.assertIn("unexpected_error", record.getMessage())
