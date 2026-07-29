"""Provider for OpenAI-compatible Chat Completions APIs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from project_akiha.providers.ai.base import ChatMessage

JSONPayload = dict[str, Any]
Headers = Mapping[str, str]
JSONTransport = Callable[[str, JSONPayload, Headers, float], JSONPayload]
JSONStreamTransport = Callable[
    [str, JSONPayload, Headers, float],
    Iterable[JSONPayload],
]
HealthTransport = Callable[[str, Headers, float], None]


class OpenAICompatibleProviderError(RuntimeError):
    """Raised when a compatible API cannot produce a usable response."""


class OpenAICompatibleProvider:
    """Generate chat responses using the shared Chat Completions schema."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_seconds: float = 60.0,
        provider_name: str = "Hosted AI",
        transport: JSONTransport | None = None,
        stream_transport: JSONStreamTransport | None = None,
        health_transport: HealthTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._provider_name = provider_name
        self._headers = _build_headers(api_key)
        self._transport = transport or _post_json
        self._stream_transport = stream_transport or _post_json_stream
        self._health_transport = health_transport or _check_models_endpoint

    async def generate_response(self, messages: Sequence[ChatMessage]) -> str:
        """Return a complete assistant response."""
        response = await asyncio.to_thread(
            self._transport,
            self._chat_url,
            self._build_payload(messages, stream=False),
            self._headers,
            self._timeout_seconds,
        )
        return _parse_chat_response(response)

    async def stream_response(
        self,
        messages: Sequence[ChatMessage],
    ) -> AsyncIterator[str]:
        """Yield assistant response chunks from an SSE response."""
        for response in self._stream_transport(
            self._chat_url,
            self._build_payload(messages, stream=True),
            self._headers,
            self._timeout_seconds,
        ):
            chunk = _parse_chat_stream_chunk(response)
            if chunk:
                yield chunk
                await asyncio.sleep(0)

    async def is_available(self) -> bool:
        """Return whether the configured provider accepts authenticated calls."""
        try:
            await asyncio.to_thread(
                self._health_transport,
                f"{self._base_url}/models",
                self._headers,
                self._timeout_seconds,
            )
        except OpenAICompatibleProviderError:
            return False
        return True

    @property
    def _chat_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _build_payload(
        self,
        messages: Sequence[ChatMessage],
        *,
        stream: bool,
    ) -> JSONPayload:
        return {
            "model": self._model,
            "stream": stream,
            "messages": [
                {"role": str(message.role), "content": message.content}
                for message in messages
            ],
        }


class UnavailableAIProvider:
    """Expose a stable configuration failure through the AI provider contract."""

    def __init__(self, detail: str) -> None:
        self._detail = detail

    async def generate_response(self, messages: Sequence[ChatMessage]) -> str:
        """Raise the configuration failure without sending message content."""
        del messages
        raise OpenAICompatibleProviderError(self._detail)

    async def stream_response(
        self,
        messages: Sequence[ChatMessage],
    ) -> AsyncIterator[str]:
        """Raise the configuration failure without sending message content."""
        del messages
        raise OpenAICompatibleProviderError(self._detail)
        yield ""

    async def is_available(self) -> bool:
        """Return false for an unavailable provider."""
        return False


def _build_headers(api_key: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _post_json(
    url: str,
    payload: JSONPayload,
    headers: Headers,
    timeout_seconds: float,
) -> JSONPayload:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=dict(headers),
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise _http_error("request", error) from error
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise OpenAICompatibleProviderError(
            "Hosted AI request failed. Check the endpoint and network connection."
        ) from error
    if not isinstance(parsed, dict):
        raise OpenAICompatibleProviderError("Hosted AI response was not a JSON object.")
    return parsed


def _post_json_stream(
    url: str,
    payload: JSONPayload,
    headers: Headers,
    timeout_seconds: float,
) -> Iterable[JSONPayload]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**dict(headers), "Accept": "text/event-stream"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    return
                parsed = json.loads(data)
                if not isinstance(parsed, dict):
                    raise OpenAICompatibleProviderError(
                        "Hosted AI stream chunk was not a JSON object."
                    )
                yield parsed
    except HTTPError as error:
        raise _http_error("stream", error) from error
    except OpenAICompatibleProviderError:
        raise
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OpenAICompatibleProviderError(
            "Hosted AI stream failed. Check the endpoint and network connection."
        ) from error


def _check_models_endpoint(
    url: str,
    headers: Headers,
    timeout_seconds: float,
) -> None:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds):
            return
    except HTTPError as error:
        raise _http_error("health check", error) from error
    except (OSError, URLError) as error:
        raise OpenAICompatibleProviderError(
            "Hosted AI health check failed. Check the endpoint and network connection."
        ) from error


def _http_error(operation: str, error: HTTPError) -> OpenAICompatibleProviderError:
    if error.code in {401, 403}:
        detail = "The hosted AI API key was rejected."
    elif error.code == 404:
        detail = "The hosted AI endpoint or model was not found."
    elif error.code == 429:
        detail = "The hosted AI rate limit or quota was reached."
    else:
        detail = f"Hosted AI {operation} failed with HTTP {error.code}."
    return OpenAICompatibleProviderError(detail)


def _parse_chat_response(response: JSONPayload) -> str:
    choice = _first_choice(response)
    message = choice.get("message")
    if not isinstance(message, dict):
        raise OpenAICompatibleProviderError(
            "Hosted AI response did not include a message."
        )
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OpenAICompatibleProviderError("Hosted AI response message was empty.")
    return content


def _parse_chat_stream_chunk(response: JSONPayload) -> str:
    choice = _first_choice(response)
    delta = choice.get("delta")
    if not isinstance(delta, dict):
        raise OpenAICompatibleProviderError(
            "Hosted AI stream chunk did not include a delta."
        )
    content = delta.get("content", "")
    if content is None:
        return ""
    if not isinstance(content, str):
        raise OpenAICompatibleProviderError("Hosted AI stream content was invalid.")
    return content


def _first_choice(response: JSONPayload) -> JSONPayload:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenAICompatibleProviderError(
            "Hosted AI response did not include any choices."
        )
    choice = choices[0]
    if not isinstance(choice, dict):
        raise OpenAICompatibleProviderError("Hosted AI response choice was invalid.")
    return choice
