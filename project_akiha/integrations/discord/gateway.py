"""Official Discord bot Gateway lifecycle with metadata-only event handling."""

from __future__ import annotations

import json
import logging
import random
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from project_akiha.config import DiscordIntegrationConfig
from project_akiha.core.integrations import ExternalEvent, ExternalService
from project_akiha.integrations.discord.normalizer import DiscordEventNormalizer
from project_akiha.services.credential_store import NamedSecretStore

DISCORD_GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
_GUILDS_INTENT = 1 << 0
_GUILD_MESSAGES_INTENT = 1 << 9
_DIRECT_MESSAGES_INTENT = 1 << 12
_INTENTS = _GUILDS_INTENT | _GUILD_MESSAGES_INTENT | _DIRECT_MESSAGES_INTENT
_MAX_GATEWAY_MESSAGE_BYTES = 1_000_000

HealthCallback = Callable[[ExternalService, str, datetime], None]


class DiscordGatewayUnavailable(RuntimeError):
    """Raised when the optional official Gateway transport is unavailable."""


class WebSocketLike(Protocol):
    """Small websocket-client surface used by the provider."""

    def send(self, payload: str) -> None:
        """Send one Gateway JSON frame."""

    def close(self) -> None:
        """Close the active connection."""

    def run_forever(self, **kwargs: object) -> object:
        """Run until closed or disconnected."""


WebSocketFactory = Callable[..., WebSocketLike]


class DiscordGatewayProvider:
    """Receive only events available to Akiha's authorized Discord bot."""

    def __init__(
        self,
        config: DiscordIntegrationConfig,
        credential_store: NamedSecretStore,
        *,
        websocket_factory: WebSocketFactory | None = None,
        on_health: HealthCallback | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config
        self._credential_store = credential_store
        self._normalizer = DiscordEventNormalizer(config)
        self._websocket_factory = websocket_factory
        self._on_health = on_health
        self._logger = logger or logging.getLogger("project_akiha.integrations.discord")
        self._health_status = "disabled" if not config.enabled else "disconnected"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._socket: WebSocketLike | None = None
        self._on_event: Callable[[ExternalEvent], None] | None = None
        self._sequence: int | None = None
        self._bot_user_id = ""

    @property
    def service(self) -> ExternalService:
        return ExternalService.DISCORD

    @property
    def health_status(self) -> str:
        return self._health_status

    def apply_config(self, config: DiscordIntegrationConfig) -> None:
        """Apply notification filters; reconnect is caller-controlled."""
        self._config = config
        self._normalizer.apply_config(config)

    def start(self, on_event: Callable[[ExternalEvent], None]) -> None:
        """Start a bounded reconnecting Gateway worker."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._on_event = on_event
        self._stop_event.clear()
        if not self._config.enabled:
            self._set_health("disabled")
            return
        if self._credential_store.get_named_secret("discord", "bot_token") is None:
            self._set_health("authentication_failure")
            return
        self._thread = threading.Thread(
            target=self._run,
            name="AkihaDiscordGateway",
            daemon=True,
        )
        self._thread.start()

    def refresh(self) -> None:
        """Reconnect so Discord can provide a fresh Gateway session."""
        socket = self._socket
        if socket is not None:
            socket.close()

    def stop(self) -> None:
        """Close Gateway and heartbeat workers without exposing the token."""
        self._stop_event.set()
        socket = self._socket
        if socket is not None:
            socket.close()
        for thread in (self._thread, self._heartbeat_thread):
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=3.0)
        self._thread = None
        self._heartbeat_thread = None
        self._socket = None
        self._on_event = None
        self._set_health("stopped")

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                factory = self._websocket_factory or _load_websocket_factory()
                self._set_health("connecting")
                socket = factory(
                    DISCORD_GATEWAY_URL,
                    on_message=self._handle_message,
                    on_error=self._handle_error,
                    on_close=self._handle_close,
                )
                self._socket = socket
                socket.run_forever(ping_interval=0)
            except DiscordGatewayUnavailable:
                self._set_health("provider_unavailable")
                return
            except Exception:
                self._logger.exception("Discord Gateway stopped safely.")
                self._set_health("provider_unavailable")
            finally:
                self._socket = None
            if self._stop_event.is_set():
                break
            self._stop_event.wait(backoff + random.random())
            backoff = min(backoff * 2, float(self._config.reconnect_max_seconds))

    def _handle_message(self, socket: WebSocketLike, raw_message: object) -> None:
        if not isinstance(raw_message, str):
            self._set_health("malformed_response")
            return
        if len(raw_message.encode("utf-8")) > _MAX_GATEWAY_MESSAGE_BYTES:
            self._set_health("malformed_response")
            return
        try:
            envelope = json.loads(raw_message)
        except json.JSONDecodeError:
            self._set_health("malformed_response")
            return
        if not isinstance(envelope, dict):
            self._set_health("malformed_response")
            return
        sequence = envelope.get("s")
        if isinstance(sequence, int):
            self._sequence = sequence
        operation = envelope.get("op")
        if operation == 10:
            self._start_heartbeat(socket, envelope.get("d"))
            self._identify(socket)
            return
        if operation == 7:
            socket.close()
            return
        if operation == 9:
            self._set_health("authentication_failure")
            socket.close()
            return
        if operation != 0:
            return
        event_name = envelope.get("t")
        data = envelope.get("d")
        if event_name == "READY" and isinstance(data, dict):
            user = data.get("user")
            user_id = user.get("id") if isinstance(user, dict) else None
            if isinstance(user_id, str) and user_id.isdecimal():
                self._bot_user_id = user_id
                self._set_health("available")
            return
        if event_name != "MESSAGE_CREATE" or not self._bot_user_id:
            return
        event = self._normalizer.normalize_message_create(
            data,
            bot_user_id=self._bot_user_id,
        )
        callback = self._on_event
        if event is not None and callback is not None and not self._stop_event.is_set():
            callback(event)

    def _identify(self, socket: WebSocketLike) -> None:
        token = self._credential_store.get_named_secret("discord", "bot_token")
        if token is None:
            self._set_health("authentication_failure")
            socket.close()
            return
        socket.send(
            json.dumps(
                {
                    "op": 2,
                    "d": {
                        "token": token,
                        "intents": _INTENTS,
                        "properties": {
                            "os": "windows",
                            "browser": "project_akiha",
                            "device": "project_akiha",
                        },
                    },
                },
                separators=(",", ":"),
            )
        )

    def _start_heartbeat(self, socket: WebSocketLike, data: object) -> None:
        if not isinstance(data, dict):
            self._set_health("malformed_response")
            socket.close()
            return
        interval_ms = data.get("heartbeat_interval")
        if not isinstance(interval_ms, int) or interval_ms <= 0:
            self._set_health("malformed_response")
            socket.close()
            return

        def heartbeat() -> None:
            interval = interval_ms / 1000
            while not self._stop_event.wait(interval):
                if self._socket is not socket:
                    return
                try:
                    socket.send(
                        json.dumps(
                            {"op": 1, "d": self._sequence},
                            separators=(",", ":"),
                        )
                    )
                except Exception:
                    socket.close()
                    return

        self._heartbeat_thread = threading.Thread(
            target=heartbeat,
            name="AkihaDiscordHeartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def _handle_error(self, _socket: WebSocketLike, _error: object) -> None:
        self._set_health("network_failure")

    def _handle_close(self, _socket: WebSocketLike, *args: object) -> None:
        del args
        if not self._stop_event.is_set():
            self._set_health("disconnected")

    def _set_health(self, status: str) -> None:
        self._health_status = status
        callback = self._on_health
        if callback is not None:
            callback(ExternalService.DISCORD, status, datetime.now(tz=UTC))


def _load_websocket_factory() -> WebSocketFactory:
    try:
        from websocket import WebSocketApp
    except ImportError as error:
        raise DiscordGatewayUnavailable(
            "Discord requires the optional websocket-client package."
        ) from error
    return WebSocketApp
