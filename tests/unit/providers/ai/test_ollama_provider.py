"""Tests for the Ollama AI provider."""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

from project_akiha.core.actions import (
    LAUNCH_APPLICATION_ACTION,
    build_default_provider_action_catalog,
)
from project_akiha.core.voice_session import SanitizedActionResult
from project_akiha.providers.ai import ChatMessage, OllamaProvider, OllamaProviderError


class OllamaProviderTest(unittest.TestCase):
    """Verify Ollama payload construction and response parsing."""

    def test_generate_response_posts_chat_payload(self) -> None:
        captured: dict[str, Any] = {}

        def transport(
            url: str,
            payload: dict[str, Any],
            timeout_seconds: float,
        ) -> dict[str, Any]:
            captured["url"] = url
            captured["payload"] = payload
            captured["timeout_seconds"] = timeout_seconds
            return {"message": {"content": "hello from ollama"}}

        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="akiha-test",
            timeout_seconds=12.0,
            transport=transport,
        )

        response = asyncio.run(
            provider.generate_response([ChatMessage(role="user", content="hi")])
        )

        self.assertEqual(response, "hello from ollama")
        self.assertEqual(captured["url"], "http://localhost:11434/api/chat")
        self.assertEqual(captured["payload"]["model"], "akiha-test")
        self.assertFalse(captured["payload"]["stream"])
        self.assertEqual(captured["timeout_seconds"], 12.0)

    def test_invalid_response_raises_provider_error(self) -> None:
        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="akiha-test",
            transport=lambda _url, _payload, _timeout: {"message": {}},
        )

        with self.assertRaises(OllamaProviderError):
            asyncio.run(
                provider.generate_response([ChatMessage(role="user", content="hi")])
            )

    def test_stream_response_yields_chat_chunks(self) -> None:
        captured: dict[str, Any] = {}

        def stream_transport(
            url: str,
            payload: dict[str, Any],
            timeout_seconds: float,
        ) -> list[dict[str, Any]]:
            captured["url"] = url
            captured["payload"] = payload
            captured["timeout_seconds"] = timeout_seconds
            return [
                {"message": {"content": "hel"}},
                {"message": {"content": "lo"}},
                {"done": True},
            ]

        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="akiha-test",
            timeout_seconds=12.0,
            stream_transport=stream_transport,
        )

        chunks = asyncio.run(
            _collect_stream(
                provider,
                [ChatMessage(role="user", content="hi")],
            )
        )

        self.assertEqual(chunks, ["hel", "lo"])
        self.assertEqual(captured["url"], "http://localhost:11434/api/chat")
        self.assertTrue(captured["payload"]["stream"])

    def test_is_available_returns_false_on_provider_error(self) -> None:
        def transport(
            _url: str,
            _payload: dict[str, Any],
            _timeout_seconds: float,
        ) -> dict[str, Any]:
            raise OllamaProviderError("offline")

        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="akiha-test",
            transport=transport,
        )

        self.assertFalse(asyncio.run(provider.is_available()))

    def test_native_tool_capability_is_loaded_once_and_cached(self) -> None:
        requests: list[tuple[str, dict[str, Any]]] = []

        def transport(
            url: str,
            payload: dict[str, Any],
            _timeout_seconds: float,
        ) -> dict[str, Any]:
            requests.append((url, payload))
            return {"capabilities": ["completion", "tools"]}

        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="tool-model",
            transport=transport,
        )

        self.assertTrue(asyncio.run(provider.supports_native_tools()))
        self.assertTrue(asyncio.run(provider.supports_native_tools()))
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0][0], "http://localhost:11434/api/show")
        self.assertEqual(requests[0][1], {"model": "tool-model"})

    def test_native_tool_capability_is_false_when_model_omits_tools(self) -> None:
        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="text-model",
            transport=lambda _url, _payload, _timeout: {"capabilities": ["completion"]},
        )

        self.assertFalse(asyncio.run(provider.supports_native_tools()))

    def test_request_native_tool_turn_builds_schema_and_proposal(self) -> None:
        captured: dict[str, Any] = {}

        def transport(
            url: str,
            payload: dict[str, Any],
            timeout_seconds: float,
        ) -> dict[str, Any]:
            captured.update(
                url=url,
                payload=payload,
                timeout_seconds=timeout_seconds,
            )
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "akiha_applications_launch",
                                "arguments": {"application_id": "spotify"},
                            }
                        }
                    ],
                }
            }

        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="tool-model",
            timeout_seconds=14.0,
            transport=transport,
        )
        catalog = build_default_provider_action_catalog()
        turn = asyncio.run(
            provider.request_native_tool_turn(
                [ChatMessage(role="user", content="Open Spotify")],
                [catalog.resolve(LAUNCH_APPLICATION_ACTION)],
                session_id="modular-session",
                turn_id="turn-native",
            )
        )

        self.assertEqual(captured["url"], "http://localhost:11434/api/chat")
        self.assertFalse(captured["payload"]["stream"])
        declaration = captured["payload"]["tools"][0]["function"]
        self.assertEqual(declaration["name"], "akiha_applications_launch")
        self.assertIn("application_id", declaration["parameters"]["required"])
        self.assertEqual(len(turn.proposals), 1)
        proposal = turn.proposals[0]
        self.assertEqual(proposal.action_name, LAUNCH_APPLICATION_ACTION)
        self.assertEqual(proposal.arguments["application_id"], "spotify")
        self.assertEqual(proposal.source, "ollama.native")

    def test_request_native_tool_turn_preserves_plain_text_response(self) -> None:
        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="tool-model",
            transport=lambda _url, _payload, _timeout: {
                "message": {"role": "assistant", "content": "No action needed."}
            },
        )

        turn = asyncio.run(
            provider.request_native_tool_turn(
                [ChatMessage(role="user", content="How are you?")],
                build_default_provider_action_catalog().schemas,
                session_id="modular-session",
                turn_id="turn-native",
            )
        )

        self.assertEqual(turn.proposals, ())
        self.assertEqual(turn.initial_text, "No action needed.")

    def test_request_native_tool_turn_rejects_unexposed_function(self) -> None:
        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="tool-model",
            transport=lambda _url, _payload, _timeout: {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "run_arbitrary_shell",
                                "arguments": {"command": "no"},
                            }
                        }
                    ]
                }
            },
        )

        with self.assertRaisesRegex(OllamaProviderError, "unexposed"):
            asyncio.run(
                provider.request_native_tool_turn(
                    [ChatMessage(role="user", content="Do something")],
                    build_default_provider_action_catalog().schemas,
                    session_id="modular-session",
                    turn_id="turn-native",
                )
            )

    def test_complete_native_tool_turn_returns_only_sanitized_result(self) -> None:
        payloads: list[dict[str, Any]] = []

        def transport(
            _url: str,
            payload: dict[str, Any],
            _timeout_seconds: float,
        ) -> dict[str, Any]:
            payloads.append(payload)
            if len(payloads) == 1:
                return {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "akiha_applications_launch",
                                    "arguments": {"application_id": "spotify"},
                                }
                            }
                        ],
                    }
                }
            return {"message": {"content": "Spotify is open."}}

        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="tool-model",
            transport=transport,
        )
        catalog = build_default_provider_action_catalog()
        turn = asyncio.run(
            provider.request_native_tool_turn(
                [ChatMessage(role="user", content="Open Spotify")],
                [catalog.resolve(LAUNCH_APPLICATION_ACTION)],
                session_id="modular-session",
                turn_id="turn-native",
            )
        )
        proposal = turn.proposals[0]
        response = asyncio.run(
            provider.complete_native_tool_turn(
                turn,
                [
                    SanitizedActionResult(
                        session_id=proposal.session_id,
                        turn_id=proposal.turn_id,
                        proposal_id=proposal.proposal_id,
                        status="success",
                        message="The approved action completed.",
                    )
                ],
            )
        )

        self.assertEqual(response, "Spotify is open.")
        follow_up = payloads[1]
        self.assertNotIn("tools", follow_up)
        tool_message = follow_up["messages"][-1]
        self.assertEqual(tool_message["role"], "tool")
        self.assertNotIn("spotify", tool_message["content"].lower())
        self.assertEqual(
            tool_message["tool_name"],
            "akiha_applications_launch",
        )


async def _collect_stream(
    provider: OllamaProvider,
    messages: list[ChatMessage],
) -> list[str]:
    return [chunk async for chunk in provider.stream_response(messages)]


if __name__ == "__main__":
    unittest.main()
