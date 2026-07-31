"""Tests for assistant-tool Qt workers."""

from __future__ import annotations

import asyncio
import unittest

from project_akiha.core.actions import (
    ActionRequest,
    ActionResult,
    ActionStatus,
    DirectorySearchMatch,
    FileSearchMatch,
    PermissionDecision,
)
from project_akiha.services.assistant_action_bridge import AssistantActionDispatch
from project_akiha.services.assistant_tool_gateway import (
    AssistantToolKind,
    AssistantToolProposal,
    MediaKind,
)
from project_akiha.ui.assistant_tool_worker import (
    AssistantDirectorySearchThread,
    AssistantMediaSearchThread,
)


class AssistantMediaSearchThreadTest(unittest.TestCase):
    def test_searches_roots_and_filters_to_requested_audio(self) -> None:
        bridge = _SearchBridge()
        proposal = AssistantToolProposal(
            AssistantToolKind.PLAY_MEDIA,
            title="Elis",
            artist="Megurine Luka",
            media_kind=MediaKind.AUDIO,
        )
        thread = AssistantMediaSearchThread(
            bridge,  # type: ignore[arg-type]
            proposal,
            (r"C:\Desktop", r"C:\Music"),
        )

        outcome = asyncio.run(thread._search())

        self.assertEqual(outcome.searched_roots, 2)
        self.assertEqual(
            tuple(match.name for match in outcome.matches),
            ("Megurine Luka - Elis.mp3",),
        )
        self.assertEqual(
            tuple(request.source for request in bridge.requests),
            ("llm_proposal", "llm_proposal"),
        )
        self.assertTrue(
            all(request.parameters["media_only"] for request in bridge.requests)
        )

    def test_directory_worker_uses_bounded_fuzzy_fallback(self) -> None:
        bridge = _DirectorySearchBridge()
        proposal = AssistantToolProposal(
            AssistantToolKind.OPEN_DIRECTORY,
            directory_name="Compressd",
            parent_name="Downloads",
        )
        thread = AssistantDirectorySearchThread(
            bridge,  # type: ignore[arg-type]
            proposal,
            (r"C:\Users\Akiha\Downloads",),
        )

        outcome = asyncio.run(thread._search())

        self.assertEqual(
            tuple(match.name for match in outcome.matches),
            ("Compressed",),
        )
        self.assertEqual(len(bridge.requests), 2)
        self.assertFalse(bridge.requests[0].parameters["match_all"])
        self.assertTrue(bridge.requests[1].parameters["match_all"])


class _SearchBridge:
    def __init__(self) -> None:
        self.requests: list[ActionRequest] = []

    async def dispatch(
        self,
        request: ActionRequest,
        *,
        confirmed: bool = False,
        cancellation_token=None,
    ) -> AssistantActionDispatch:
        del confirmed, cancellation_token
        self.requests.append(request)
        root = str(request.parameters["root"])
        matches = (
            (
                _match(
                    "Megurine Luka - Elis.mp3",
                    rf"{root}\Solitude\Megurine Luka - Elis.mp3",
                ),
                _match("Elis.mp4", rf"{root}\Video\Elis.mp4"),
            )
            if root.endswith("Desktop")
            else ()
        )
        result = ActionResult(
            correlation_id=request.correlation_id,
            action_id=request.action_id,
            status=ActionStatus.SUCCESS,
            summary=f"Found {len(matches)} matching file(s).",
            permission_decision=PermissionDecision.GRANTED,
            metadata={"matches": matches},
        )
        return AssistantActionDispatch(request=request, result=result)


class _DirectorySearchBridge:
    def __init__(self) -> None:
        self.requests: list[ActionRequest] = []

    async def dispatch(
        self,
        request: ActionRequest,
        *,
        confirmed: bool = False,
        cancellation_token=None,
    ) -> AssistantActionDispatch:
        del confirmed, cancellation_token
        self.requests.append(request)
        matches = (
            (
                DirectorySearchMatch(
                    name="Compressed",
                    path=rf"{request.parameters['root']}\Compressed",
                    modified_at="2026-07-31T00:00:00+00:00",
                ),
            )
            if request.parameters["match_all"]
            else ()
        )
        result = ActionResult(
            correlation_id=request.correlation_id,
            action_id=request.action_id,
            status=ActionStatus.SUCCESS,
            summary=f"Found {len(matches)} matching directories.",
            permission_decision=PermissionDecision.GRANTED,
            metadata={"matches": matches},
        )
        return AssistantActionDispatch(request=request, result=result)


def _match(name: str, path: str) -> FileSearchMatch:
    return FileSearchMatch(
        name=name,
        path=path,
        size_bytes=10,
        modified_at="2026-07-31T00:00:00+00:00",
    )


if __name__ == "__main__":
    unittest.main()
