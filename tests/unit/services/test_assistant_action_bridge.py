"""Tests for explicit direct chat-to-action request bridging."""

from __future__ import annotations

import asyncio
import unittest

from project_akiha.core.actions import (
    ActionRequest,
    ActionResult,
    ActionStatus,
    PermissionDecision,
)
from project_akiha.services.assistant_action_bridge import (
    AssistantActionBridge,
    AssistantActionRequestParser,
)


class AssistantActionRequestParserTest(unittest.TestCase):
    """Verify only explicit command forms become typed requests."""

    def setUp(self) -> None:
        self.parser = AssistantActionRequestParser()

    def test_parses_open_directory_command_with_spaces(self) -> None:
        request = self.parser.parse(
            r"open directory: C:\Users\Akiha\Project Files",
            correlation_id="chat-1",
        )

        self.assertIsNotNone(request)
        self.assertEqual(request.correlation_id, "chat-1")
        self.assertEqual(request.action_id, "files.open_directory")
        self.assertEqual(
            request.parameters["path"],
            r"C:\Users\Akiha\Project Files",
        )

    def test_parses_search_command_with_explicit_separator(self) -> None:
        request = self.parser.parse(
            r"search files: report | C:\Users\Akiha\Documents",
            correlation_id="chat-2",
        )

        self.assertIsNotNone(request)
        self.assertEqual(request.action_id, "files.search")
        self.assertEqual(request.parameters["query"], "report")
        self.assertEqual(
            request.parameters["root"],
            r"C:\Users\Akiha\Documents",
        )

    def test_ordinary_conversation_does_not_become_an_action(self) -> None:
        self.assertIsNone(self.parser.parse("Could you open the directory later?"))
        self.assertIsNone(self.parser.parse("Please help me plan today."))

    def test_empty_command_does_not_become_an_action(self) -> None:
        self.assertIsNone(self.parser.parse("open directory"))
        self.assertIsNone(self.parser.parse("search files: report"))


class AssistantActionBridgeTest(unittest.TestCase):
    """Verify dispatch requires a typed request and preserves the result."""

    def test_dispatches_typed_request_to_action_service(self) -> None:
        service = _RecordingActionService()
        bridge = AssistantActionBridge(service)  # type: ignore[arg-type]
        request = ActionRequest(
            correlation_id="chat-3",
            action_id="files.open_directory",
            source="chat",
            parameters={"path": r"C:\Users\Akiha\Documents"},
        )

        dispatch = asyncio.run(bridge.dispatch(request))

        self.assertEqual(dispatch.request, request)
        self.assertEqual(dispatch.result.status, ActionStatus.SUCCESS)
        self.assertEqual(service.requests, [request])

    def test_dispatch_rejects_plain_text(self) -> None:
        bridge = AssistantActionBridge(_RecordingActionService())  # type: ignore[arg-type]

        with self.assertRaises(TypeError):
            asyncio.run(bridge.dispatch("open folder"))  # type: ignore[arg-type]


class _RecordingActionService:
    def __init__(self) -> None:
        self.requests: list[ActionRequest] = []

    async def evaluate_request(
        self,
        request: ActionRequest,
        *,
        confirmed: bool,
        cancellation_token,
    ) -> ActionResult:
        del confirmed, cancellation_token
        self.requests.append(request)
        return ActionResult(
            correlation_id=request.correlation_id,
            action_id=request.action_id,
            status=ActionStatus.SUCCESS,
            summary="The approved directory was opened.",
            permission_decision=PermissionDecision.GRANTED,
        )


if __name__ == "__main__":
    unittest.main()
