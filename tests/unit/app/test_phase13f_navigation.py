"""Contextual navigation through the real composer and search callbacks."""

import asyncio
import hashlib
import json
import unittest

from project_akiha.core.actions import ActionStatus, DirectorySearchMatch
from project_akiha.ui.assistant_tool_worker import DirectorySearchOutcome
from tests.unit.app import test_phase13b_composition as composition


class ContextualNavigationCompositionTest(unittest.TestCase):
    release_graph = composition.Phase13BCompositionTest.release_graph
    send = composition.Phase13BCompositionTest.send
    wait_chat = composition.Phase13BCompositionTest.wait_chat

    @classmethod
    def setUpClass(cls):
        composition.Phase13BCompositionTest.setUpClass()
        cls.app = composition.Phase13BCompositionTest.app

    def setUp(self):
        composition.Phase13BCompositionTest.setUp(self)
        self.album = self.approved / "Album"
        self.album.mkdir()
        self.state["ephemeral_action_context"].record_directory(str(self.album))

    def test_contextual_name_binds_search_to_current_approved_directory(self):
        self.send("Open Compressed folder inside it")
        identity = self.leases._local_search
        self.assertIsNotNone(identity)
        self.assertEqual(
            identity.request.parameters["roots_digest"],
            hashlib.sha256(json.dumps((str(self.album),)).encode()).hexdigest(),
        )
        self.assertEqual(self.provider.prompts, [])
        child = self.album / "Compressed"
        child.mkdir()
        worker = composition._ControlledSearch.created[-1]
        worker.result_ready.emit(
            DirectorySearchOutcome(
                (DirectorySearchMatch("Compressed", str(child), "now"),), 1, True, False
            )
        )
        action = composition._ControlledAction.created[-1]
        self.assertEqual(action._request.parameters["path"], str(child))
        self.assertTrue(action._ownership_guard())

    def test_ambiguous_contextual_result_asks_and_supersession_rejects_late_result(
        self,
    ):
        self.send("Open Compressed folder inside it")
        worker = composition._ControlledSearch.created[-1]
        matches = tuple(
            DirectorySearchMatch("Compressed", str(self.album / str(i)), "now")
            for i in range(2)
        )
        worker.result_ready.emit(DirectorySearchOutcome(matches, 1, True, False))
        self.assertEqual(len(self.leases.pending.choices), 2)
        self.send("Open an app")
        newer = self.leases.pending
        worker.result_ready.emit(DirectorySearchOutcome(matches[:1], 1, True, False))
        self.assertEqual(self.leases.pending, newer)
        self.assertEqual(composition._ControlledAction.created, [])

    def test_revoked_context_never_opens_or_reads_private_files(self):
        self.send("Open Compressed folder inside it")
        worker = composition._ControlledSearch.created[-1]
        permissions = self.state["assistant_permission_service"]
        grants = asyncio.run(permissions.get_active_permissions())
        for grant in grants:
            asyncio.run(permissions.revoke(grant.id))
        worker.result_ready.emit(
            DirectorySearchOutcome(
                (
                    DirectorySearchMatch(
                        "Compressed", str(self.album / "Compressed"), "now"
                    ),
                ),
                1,
                True,
                False,
            )
        )
        self.assertEqual(composition._ControlledAction.created, [])
        self.assertIsNone(self.leases.pending)

    def test_outside_root_callback_is_rejected(self):
        self.send("Open Compressed folder inside it")
        worker = composition._ControlledSearch.created[-1]
        worker.result_ready.emit(
            DirectorySearchOutcome(
                (
                    DirectorySearchMatch(
                        "Compressed", str(self.root / "outside"), "now"
                    ),
                ),
                1,
                True,
                False,
            )
        )
        action = composition._ControlledAction.created[-1]
        dispatch = asyncio.run(action._dispatch())
        self.assertIs(dispatch.result.status, ActionStatus.DENIED)
        self.assertIsNone(self.leases.pending)
