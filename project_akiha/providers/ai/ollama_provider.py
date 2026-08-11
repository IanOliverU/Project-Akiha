"""Ollama-backed AI provider."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from project_akiha.core.actions import (
    ActionToolSchema,
    ParameterKind,
)
from project_akiha.core.voice_session import ActionProposal, SanitizedActionResult
from project_akiha.providers.ai.base import ChatMessage

JSONPayload = dict[str, Any]
JSONTransport = Callable[[str, JSONPayload, float], JSONPayload]
JSONStreamTransport = Callable[[str, JSONPayload, float], Iterable[JSONPayload]]
_MAX_NATIVE_TOOL_CALLS = 8


@dataclass(frozen=True, slots=True)
class OllamaNativeToolTurn:
    """One bounded Ollama response and its provider-neutral proposals."""

    session_id: str
    turn_id: str
    proposals: tuple[ActionProposal, ...]
    initial_text: str = ""
    _request_messages_json: str = field(default="", repr=False)
    _assistant_message_json: str = field(default="", repr=False)
    _tool_names: tuple[str, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        if len(self.proposals) != len(self._tool_names):
            raise ValueError("Ollama proposals and tool names must remain aligned.")


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
        stream_transport: JSONStreamTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._transport = transport or _post_json
        self._stream_transport = stream_transport or _post_json_stream
        self._native_tools_supported: bool | None = None

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

    async def stream_response(
        self,
        messages: Sequence[ChatMessage],
    ) -> AsyncIterator[str]:
        """Yield assistant response chunks from Ollama."""
        payload = {
            "model": self._model,
            "stream": True,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
        }

        for response in self._stream_transport(
            f"{self._base_url}/api/chat",
            payload,
            self._timeout_seconds,
        ):
            chunk = _parse_chat_stream_chunk(response)
            if chunk:
                yield chunk
                await asyncio.sleep(0)

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

    async def supports_native_tools(self) -> bool:
        """Return whether the selected Ollama model reports tool capability."""
        cached = self._native_tools_supported
        if cached is not None:
            return cached
        response = await asyncio.to_thread(
            self._transport,
            f"{self._base_url}/api/show",
            {"model": self._model},
            self._timeout_seconds,
        )
        capabilities = response.get("capabilities")
        supported = bool(
            isinstance(capabilities, list)
            and all(isinstance(item, str) for item in capabilities)
            and "tools" in capabilities
        )
        self._native_tools_supported = supported
        return supported

    async def request_native_tool_turn(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ActionToolSchema],
        *,
        session_id: str,
        turn_id: str,
    ) -> OllamaNativeToolTurn:
        """Request one non-streaming native tool decision from Ollama."""
        declarations, action_names = _build_tool_declarations(tools)
        request_messages = [
            {"role": message.role, "content": message.content} for message in messages
        ]
        response = await asyncio.to_thread(
            self._transport,
            f"{self._base_url}/api/chat",
            {
                "model": self._model,
                "stream": False,
                "messages": request_messages,
                "tools": declarations,
            },
            self._timeout_seconds,
        )
        return _parse_native_tool_turn(
            response,
            request_messages=request_messages,
            action_names=action_names,
            session_id=session_id,
            turn_id=turn_id,
        )

    async def complete_native_tool_turn(
        self,
        turn: OllamaNativeToolTurn,
        results: Sequence[SanitizedActionResult],
    ) -> str:
        """Return sanitized results to Ollama and obtain final canonical text."""
        if len(results) != len(turn.proposals):
            raise OllamaProviderError("Ollama tool results did not match tool calls.")
        request_messages = _require_json_list(turn._request_messages_json)
        assistant_message = _require_json_object(turn._assistant_message_json)
        tool_messages: list[JSONPayload] = []
        for proposal, tool_name, result in zip(
            turn.proposals,
            turn._tool_names,
            results,
            strict=True,
        ):
            if (
                result.session_id != proposal.session_id
                or result.turn_id != proposal.turn_id
                or result.proposal_id != proposal.proposal_id
            ):
                raise OllamaProviderError(
                    "Ollama tool result ownership did not match its proposal."
                )
            tool_messages.append(
                {
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": json.dumps(
                        {
                            "status": result.status,
                            "message": result.message,
                        },
                        ensure_ascii=True,
                        separators=(",", ":"),
                    ),
                }
            )
        response = await asyncio.to_thread(
            self._transport,
            f"{self._base_url}/api/chat",
            {
                "model": self._model,
                "stream": False,
                "messages": [
                    *request_messages,
                    assistant_message,
                    *tool_messages,
                ],
            },
            self._timeout_seconds,
        )
        return _parse_chat_response(response)


def _build_tool_declarations(
    schemas: Sequence[ActionToolSchema],
) -> tuple[list[JSONPayload], dict[str, str]]:
    declarations: list[JSONPayload] = []
    action_names: dict[str, str] = {}
    for schema in schemas:
        tool_name = _tool_name(schema.action_id)
        if tool_name in action_names:
            raise OllamaProviderError("Ollama tool names must be unique.")
        action_names[tool_name] = schema.action_id
        properties: JSONPayload = {}
        required: list[str] = []
        for parameter in schema.parameters:
            property_schema: JSONPayload = {
                "type": {
                    ParameterKind.STRING: "string",
                    ParameterKind.INTEGER: "integer",
                    ParameterKind.BOOLEAN: "boolean",
                }[parameter.kind]
            }
            if parameter.max_length is not None:
                property_schema["maxLength"] = parameter.max_length
            if parameter.allowed_values:
                property_schema["enum"] = list(parameter.allowed_values)
            if parameter.minimum_value is not None:
                property_schema["minimum"] = parameter.minimum_value
            if parameter.maximum_value is not None:
                property_schema["maximum"] = parameter.maximum_value
            properties[parameter.name] = property_schema
            if parameter.required:
                required.append(parameter.name)
        declarations.append(
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": schema.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                        "additionalProperties": False,
                    },
                },
            }
        )
    return declarations, action_names


def _parse_native_tool_turn(
    response: JSONPayload,
    *,
    request_messages: list[JSONPayload],
    action_names: Mapping[str, str],
    session_id: str,
    turn_id: str,
) -> OllamaNativeToolTurn:
    message = response.get("message")
    if not isinstance(message, dict):
        raise OllamaProviderError("Ollama response did not include a message.")
    raw_calls = message.get("tool_calls", [])
    if not isinstance(raw_calls, list):
        raise OllamaProviderError("Ollama tool calls were invalid.")
    if len(raw_calls) > _MAX_NATIVE_TOOL_CALLS:
        raise OllamaProviderError("Ollama returned too many tool calls.")
    if not raw_calls:
        return OllamaNativeToolTurn(
            session_id=session_id,
            turn_id=turn_id,
            proposals=(),
            initial_text=_parse_message_content(message),
            _request_messages_json=json.dumps(request_messages),
            _assistant_message_json=json.dumps(message),
        )

    proposals: list[ActionProposal] = []
    tool_names: list[str] = []
    for index, raw_call in enumerate(raw_calls):
        if not isinstance(raw_call, dict):
            raise OllamaProviderError("Ollama tool call was invalid.")
        function = raw_call.get("function")
        if not isinstance(function, dict):
            raise OllamaProviderError("Ollama tool call omitted its function.")
        tool_name = function.get("name")
        arguments = function.get("arguments", {})
        if not isinstance(tool_name, str) or tool_name not in action_names:
            raise OllamaProviderError("Ollama proposed an unexposed tool.")
        if not isinstance(arguments, dict):
            raise OllamaProviderError("Ollama tool arguments were invalid.")
        proposal_id = _proposal_id(turn_id, index, tool_name, arguments)
        try:
            proposal = ActionProposal(
                session_id=session_id,
                turn_id=turn_id,
                proposal_id=proposal_id,
                source="ollama.native",
                action_name=action_names[tool_name],
                arguments=arguments,
            )
        except (TypeError, ValueError) as error:
            raise OllamaProviderError("Ollama tool arguments were unsafe.") from error
        proposals.append(proposal)
        tool_names.append(tool_name)
    return OllamaNativeToolTurn(
        session_id=session_id,
        turn_id=turn_id,
        proposals=tuple(proposals),
        _request_messages_json=json.dumps(request_messages),
        _assistant_message_json=json.dumps(message),
        _tool_names=tuple(tool_names),
    )


def _parse_message_content(message: Mapping[str, object]) -> str:
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OllamaProviderError("Ollama response contained no text or tool call.")
    return content.strip()


def _tool_name(action_id: str) -> str:
    return f"akiha_{action_id.replace('.', '_').replace('-', '_')}"


def _proposal_id(
    turn_id: str,
    index: int,
    tool_name: str,
    arguments: Mapping[str, object],
) -> str:
    encoded = json.dumps(
        arguments,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(
        f"{turn_id}\0{index}\0{tool_name}\0{encoded}".encode()
    ).hexdigest()[:32]
    return f"ollama-{digest}"


def _require_json_list(payload: str) -> list[JSONPayload]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise OllamaProviderError("Ollama turn context was invalid.") from error
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise OllamaProviderError("Ollama turn messages were invalid.")
    return value


def _require_json_object(payload: str) -> JSONPayload:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise OllamaProviderError("Ollama turn context was invalid.") from error
    if not isinstance(value, dict):
        raise OllamaProviderError("Ollama assistant tool message was invalid.")
    return value


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


def _post_json_stream(
    url: str,
    payload: JSONPayload,
    timeout_seconds: float,
) -> Iterable[JSONPayload]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            for line in response:
                if not line.strip():
                    continue
                parsed = json.loads(line.decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise OllamaProviderError(
                        "Ollama stream chunk was not a JSON object."
                    )
                yield parsed
    except (OSError, URLError, json.JSONDecodeError) as error:
        message = f"Ollama stream failed: {error}"
        raise OllamaProviderError(message) from error


def _parse_chat_response(response: JSONPayload) -> str:
    message = response.get("message")
    if not isinstance(message, dict):
        raise OllamaProviderError("Ollama response did not include a message.")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OllamaProviderError("Ollama response message was empty.")

    return content


def _parse_chat_stream_chunk(response: JSONPayload) -> str:
    message = response.get("message")
    if message is None and response.get("done") is True:
        return ""
    if not isinstance(message, dict):
        raise OllamaProviderError("Ollama stream chunk did not include a message.")

    content = message.get("content", "")
    if not isinstance(content, str):
        raise OllamaProviderError("Ollama stream chunk content was invalid.")

    return content
