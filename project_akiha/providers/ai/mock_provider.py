"""Deterministic mock provider for the Phase 2 chat shell."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from project_akiha.providers.ai.base import ChatMessage


class MockAIProvider:
    """Return local deterministic responses while real AI is not wired yet."""

    async def generate_response(self, messages: Sequence[ChatMessage]) -> str:
        """Return a short mock response based on the latest user message."""
        await asyncio.sleep(0)
        latest_user_message = _latest_user_message(messages)
        if latest_user_message is None:
            return "I'm here."

        return f"I heard you say: {latest_user_message.content}"

    async def stream_response(
        self,
        messages: Sequence[ChatMessage],
    ) -> AsyncIterator[str]:
        """Yield a deterministic response in small chunks."""
        response = await self.generate_response(messages)
        for chunk in _chunk_response(response):
            await asyncio.sleep(0)
            yield chunk

    async def is_available(self) -> bool:
        """Return true because the mock provider is always local."""
        await asyncio.sleep(0)
        return True


def _latest_user_message(messages: Sequence[ChatMessage]) -> ChatMessage | None:
    for message in reversed(messages):
        if message.role == "user":
            return message
    return None


def _chunk_response(response: str, chunk_size: int = 12) -> tuple[str, ...]:
    return tuple(
        response[index : index + chunk_size]
        for index in range(0, len(response), chunk_size)
    )
