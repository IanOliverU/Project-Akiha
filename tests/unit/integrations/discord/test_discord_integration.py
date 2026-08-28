"""Tests for the official bot-scoped Discord integration."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime

from project_akiha.config import DiscordIntegrationConfig
from project_akiha.core.integrations import ExternalEventKind
from project_akiha.integrations.discord.gateway import DiscordGatewayProvider
from project_akiha.integrations.discord.normalizer import DiscordEventNormalizer


class DiscordNormalizerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.normalizer = DiscordEventNormalizer(
            DiscordIntegrationConfig(
                notify_authorized_channels=True,
                authorized_channel_ids=("222",),
                owner_user_id="555",
            )
        )
        self.now = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)

    def test_dm_to_bot_contains_metadata_but_not_message_content(self) -> None:
        event = self.normalizer.normalize_message_create(
            _message(content="private message body"),
            bot_user_id="999",
            received_at=self.now,
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.kind, ExternalEventKind.DISCORD_BOT_DIRECT_MESSAGE)
        self.assertFalse(hasattr(event, "content"))
        self.assertNotIn("private message body", repr(event))

    def test_mention_and_authorized_channel_are_bounded(self) -> None:
        mention = self.normalizer.normalize_message_create(
            _message(guild_id="111", mentions=[{"id": "999"}]),
            bot_user_id="999",
            received_at=self.now,
        )
        channel = self.normalizer.normalize_message_create(
            _message(guild_id="111", channel_id="222"),
            bot_user_id="999",
            received_at=self.now,
        )

        self.assertEqual(mention.kind, ExternalEventKind.DISCORD_MENTION)
        self.assertEqual(
            channel.kind,
            ExternalEventKind.DISCORD_AUTHORIZED_CHANNEL_MESSAGE,
        )

    def test_owner_mention_and_reply_use_structured_user_ids(self) -> None:
        mention = self.normalizer.normalize_message_create(
            _message(guild_id="111", mentions=[{"id": "555"}]),
            bot_user_id="999",
            received_at=self.now,
        )
        reply = self.normalizer.normalize_message_create(
            _message(
                guild_id="111",
                referenced_message={"author": {"id": "555"}},
            ),
            bot_user_id="999",
            received_at=self.now,
        )

        self.assertEqual(mention.kind, ExternalEventKind.DISCORD_OWNER_MENTION)
        self.assertEqual(reply.kind, ExternalEventKind.DISCORD_OWNER_REPLY)

    def test_owner_username_without_matching_id_is_not_trusted(self) -> None:
        event = self.normalizer.normalize_message_create(
            _message(
                guild_id="111",
                mentions=[{"id": "444", "username": "hanekanyan"}],
            ),
            bot_user_id="999",
            received_at=self.now,
        )

        self.assertIsNone(event)

    def test_unapproved_or_malformed_context_is_rejected(self) -> None:
        cases = (
            _message(guild_id="111", channel_id="333"),
            _message(guild_id="not-a-snowflake"),
            _message(author={"id": "999", "username": "Akiha"}),
            _message(author={"id": "777", "username": "Bot", "bot": True}),
        )
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertIsNone(
                    self.normalizer.normalize_message_create(
                        payload,
                        bot_user_id="999",
                        received_at=self.now,
                    )
                )


class DiscordGatewayTest(unittest.TestCase):
    def test_identify_uses_bot_token_only_in_gateway_frame(self) -> None:
        socket = _Socket()
        provider = DiscordGatewayProvider(
            DiscordIntegrationConfig(enabled=True),
            _SecretStore("discord-bot-token"),
        )

        provider._identify(socket)

        frame = json.loads(socket.sent[0])
        self.assertEqual(frame["op"], 2)
        self.assertEqual(frame["d"]["token"], "discord-bot-token")
        self.assertNotIn("content", frame["d"])

    def test_ready_then_message_emits_sanitized_event(self) -> None:
        events = []
        health = []
        provider = DiscordGatewayProvider(
            DiscordIntegrationConfig(enabled=True),
            _SecretStore("token"),
            on_health=lambda service, status, checked: health.append(
                (service.value, status, checked)
            ),
        )
        provider._on_event = events.append
        socket = _Socket()

        provider._handle_message(
            socket,
            json.dumps({"op": 0, "t": "READY", "s": 1, "d": {"user": {"id": "999"}}}),
        )
        provider._handle_message(
            socket,
            json.dumps({"op": 0, "t": "MESSAGE_CREATE", "s": 2, "d": _message()}),
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].external_id, "123")
        self.assertFalse(hasattr(events[0], "content"))
        self.assertEqual(health[-1][1], "available")

    def test_missing_token_fails_closed_without_worker(self) -> None:
        health = []
        provider = DiscordGatewayProvider(
            DiscordIntegrationConfig(enabled=True),
            _SecretStore(None),
            on_health=lambda service, status, checked: health.append(status),
        )

        provider.start(lambda _event: None)

        self.assertEqual(provider.health_status, "authentication_failure")
        self.assertEqual(health[-1], "authentication_failure")


class _SecretStore:
    def __init__(self, token: str | None) -> None:
        self.token = token

    def get_named_secret(self, namespace: str, name: str) -> str | None:
        self.assert_key(namespace, name)
        return self.token

    def set_named_secret(self, namespace: str, name: str, secret: str) -> None:
        self.assert_key(namespace, name)
        self.token = secret

    def delete_named_secret(self, namespace: str, name: str) -> None:
        self.assert_key(namespace, name)
        self.token = None

    @staticmethod
    def assert_key(namespace: str, name: str) -> None:
        if (namespace, name) != ("discord", "bot_token"):
            raise AssertionError("Unexpected secret namespace.")


class _Socket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    def send(self, payload: str) -> None:
        self.sent.append(payload)

    def close(self) -> None:
        self.closed = True

    def run_forever(self, **kwargs: object) -> object:
        del kwargs
        return None


def _message(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "123",
        "channel_id": "456",
        "author": {"id": "777", "username": "Sender"},
        "timestamp": "2026-08-27T12:00:00Z",
        "mentions": [],
        "content": "must remain outside the typed event",
    }
    payload.update(changes)
    return payload


if __name__ == "__main__":
    unittest.main()
