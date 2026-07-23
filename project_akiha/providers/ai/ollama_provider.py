"""Ollama-backed AI provider."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Sequence
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from project_akiha.providers.ai.base import ChatMessage

JSONPayload = dict[str, Any]
JSONTransport = Callable[[str, JSONPayload, float], JSONPayload]


class OllamaProviderError(RuntimeError):
    """Raised when Ollama cannot produce a usable response."""


class OllamaProvider:
    """Generate chat responses through Ollama's local HTTP API."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
        transport: JSONTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._transport = transport or _post_json

    async def generate_response(self, messages: Sequence[ChatMessage]) -> str:
        """Return a complete assistant response from Ollama."""
        payload = {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
        }
        response = await asyncio.to_thread(
            self._transport,
            f"{self._base_url}/api/chat",
            payload,
            self._timeout_seconds,
        )
        return _parse_chat_response(response)

    async def is_available(self) -> bool:
        """Return whether Ollama answers a local version request."""
        try:
            await asyncio.to_thread(
                self._transport,
                f"{self._base_url}/api/version",
                {},
                self._timeout_seconds,
            )
        except OllamaProviderError:
            return False
        return True


def _post_json(url: str, payload: JSONPayload, timeout_seconds: float) -> JSONPayload:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as error:
        message = f"Ollama request failed: {error}"
        raise OllamaProviderError(message) from error

    if not isinstance(parsed, dict):
        raise OllamaProviderError("Ollama response was not a JSON object.")

    return parsed


def _parse_chat_response(response: JSONPayload) -> str:
    message = response.get("message")
    if not isinstance(message, dict):
        raise OllamaProviderError("Ollama response did not include a message.")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OllamaProviderError("Ollama response message was empty.")

    return content
