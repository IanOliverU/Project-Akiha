"""Selected export integrity, confirmation, atomic ownership and private boundaries."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

from project_akiha.core.actions import (
    ActionCancellationToken,
    ActionPermissionPolicy,
    ActionRequest,
    ActionRequestValidator,
    PermissionDecision,
    ProtectedPathPolicy,
    build_default_action_registry,
)
from project_akiha.database.migrator import DatabaseMigrator
from project_akiha.services.action_clarification import ActionClarificationService
from project_akiha.services.user_export import MAX_EXPORT_BYTES, UserExportService
from tests.unit.services.test_phase13c_timers import FakeClock


class UserExportTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "data.sqlite3"
        DatabaseMigrator(self.db).apply_pending()
        with closing(sqlite3.connect(self.db)) as c, c:
            for identifier, text in [
                (1, "SELECTED_TEXT"),
                (2, "UNSELECTED_PRIVATE_SENTINEL"),
            ]:
                c.execute(
                    (
                        "INSERT INTO "
                        "conversations(id,title,created_at,updated_at) "
                        "VALUES (?,?,'2026-10-09','2026-10-09')"
                    ),
                    (identifier, "Chat " + str(identifier)),
                )
                c.execute(
                    (
                        "INSERT INTO "
                        "messages(conversation_id,role,content,created_at"
                        ") VALUES (?,'user',?,'2026-10-09')"
                    ),
                    (identifier, text),
                )
            c.execute(
                "INSERT INTO "
                "messages(conversation_id,role,content,created_at"
                ") VALUES (1,'system','SYSTEM_PROVIDER_SENTINEL',"
                "'2026-10-09')"
            )
            c.execute(
                "INSERT INTO "
                "memories(id,content,created_at,updated_at) "
                "VALUES (1,'SELECTED_MEMORY','2026-10-09','2026-1"
                "0-09')"
            )
            c.execute(
                "INSERT INTO "
                "notification_inbox(service,event_kind,priority,d"
                "isplay_text,occurred_at,created_at,delivery_stat"
                "us) VALUES "
                "('timers','timers.elapsed','normal','NOTIFICATIO"
                "N_PRIVATE_SENTINEL','2026-10-09','2026-10-09','s"
                "ilent')"
            )
        self.clock = FakeClock()
        self.registry = build_default_action_registry()
        self.leases = ActionClarificationService(self.registry, clock=self.clock)
        self.policy = ProtectedPathPolicy()
        self.service = UserExportService(
            self.db,
            self.policy,
            clock=lambda: self.clock.mono,
            commit_guard=self.leases.commit_owned,
        )
        self.destination = self.root / "selected.json"
        self.token = ActionCancellationToken()

    def prepared(self, kind="conversations"):
        request = self.service.prepare(kind, (1,), self.destination)
        epoch = self.leases.claim(request)
        self.service.bind_owner(request, epoch)
        return request, epoch

    def confirmed(self, kind="conversations"):
        request, epoch = self.prepared(kind)
        lease = self.leases.issue_confirmation(request, owner_epoch=epoch)
        self.assertTrue(self.leases.consume_confirmation(lease, request, approved=True))
        self.service.authorize_confirmed(request, epoch)
        return request, epoch

    def test_selected_conversation_manifest_integrity_and_exclusions(self):
        request, _ = self.confirmed()
        self.service.write(request, self.token)
        data = json.loads(self.destination.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["manifest"]["selected_ids"], [1])
        serialized = json.dumps(
            data["records"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        self.assertEqual(
            data["manifest"]["records_sha256"], hashlib.sha256(serialized).hexdigest()
        )
        text = self.destination.read_text(encoding="utf-8")
        self.assertIn("SELECTED_TEXT", text)
        for secret in [
            "UNSELECTED_PRIVATE_SENTINEL",
            "SYSTEM_PROVIDER_SENTINEL",
            "NOTIFICATION_PRIVATE_SENTINEL",
            "SELECTED_MEMORY",
        ]:
            self.assertNotIn(secret, text)
        self.assertEqual(list(self.root.glob(".akiha-export-*")), [])

    def test_selected_memory_does_not_export_conversations_or_embeddings(self):
        request, _ = self.confirmed("memories")
        self.service.write(request, self.token)
        text = self.destination.read_text(encoding="utf-8")
        self.assertIn("SELECTED_MEMORY", text)
        self.assertNotIn("SELECTED_TEXT", text)
        self.assertEqual(
            set(json.loads(text)["records"][0]),
            {"id", "text", "importance", "created_at", "updated_at"},
        )

    def test_unconfirmed_draft_never_writes(self):
        request, _ = self.prepared()
        with self.assertRaises(ValueError):
            self.service.write(request, self.token)
        self.assertFalse(self.destination.exists())

    def test_exact_expiry_boundary_rejects(self):
        request, _ = self.confirmed()
        self.clock.advance(60)
        with self.assertRaises(ValueError):
            self.service.write(request, self.token)
        self.assertFalse(self.destination.exists())

    def test_replay_and_changed_fingerprint_reject(self):
        request, epoch = self.confirmed()
        forged = replace(request, correlation_id="forged-export")
        with self.assertRaises(ValueError):
            self.service.write(forged, self.token)
        self.service.write(request, self.token)
        original = self.destination.read_bytes()
        with self.assertRaises(ValueError):
            self.service.write(request, self.token)
        self.assertEqual(self.destination.read_bytes(), original)

    def test_cancel_revocation_and_supersession_prevent_publication(self):
        for outcome in ["cancel", "invalidate", "supersede"]:
            with self.subTest(outcome=outcome):
                request, _ = self.confirmed()
                if outcome == "cancel":
                    self.token.cancel()
                elif outcome == "invalidate":
                    self.service.invalidate()
                else:
                    self.leases.claim(
                        ActionRequest(
                            "new-action",
                            "applications.launch",
                            "chat",
                            {"application_id": "spotify"},
                        )
                    )
                with self.assertRaises(ValueError):
                    self.service.write(request, self.token)
                self.assertFalse(self.destination.exists())
                self.token = ActionCancellationToken()

    def test_supersession_at_atomic_commit_boundary(self):
        request, _ = self.confirmed()
        arrived = Event()
        release = Event()

        def guarded(req, epoch, commit):
            arrived.set()
            self.assertTrue(release.wait(5))
            return self.leases.commit_owned(req, epoch, commit)

        self.service.commit_guard = guarded
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.service.write, request, self.token)
            self.assertTrue(arrived.wait(5))
            self.leases.claim(
                ActionRequest(
                    "new-action",
                    "applications.launch",
                    "chat",
                    {"application_id": "spotify"},
                )
            )
            release.set()
            with self.assertRaises(ValueError):
                pending.result(5)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob(".akiha-export-*")), [])

    def test_existing_and_competing_files_never_overwritten(self):
        self.destination.write_text("existing")
        with self.assertRaises(ValueError):
            self.prepared()
        self.destination.unlink()
        request, _ = self.confirmed()

        def guarded(req, epoch, commit):
            self.destination.write_text("competing owner file")
            return self.leases.commit_owned(req, epoch, commit)

        self.service.commit_guard = guarded
        with self.assertRaises(ValueError):
            self.service.write(request, self.token)
        self.assertEqual(self.destination.read_text(), "competing owner file")

    def test_missing_selected_record_is_atomic_failure(self):
        request, _ = self.confirmed()
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("DELETE FROM conversations WHERE id=1")
        with self.assertRaises(ValueError):
            self.service.write(request, self.token)
        self.assertFalse(self.destination.exists())

    def test_oversized_selection_fails_before_temporary_write(self):
        request, _ = self.confirmed()
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute(
                "UPDATE messages SET content=? WHERE conversation_id=1 AND role='user'",
                ("x" * (MAX_EXPORT_BYTES + 1),),
            )
        with self.assertRaises(ValueError):
            self.service.write(request, self.token)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob(".akiha-export-*")), [])

    def test_write_failure_leaves_no_output_and_no_private_tempfile(self):
        request, _ = self.confirmed()
        with patch(
            "project_akiha.services.user_export.os.link",
            side_effect=OSError("synthetic unsupported filesystem"),
        ):
            with self.assertRaises(OSError):
                self.service.write(request, self.token)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob(".akiha-export-*")), [])

    def test_destination_and_selection_validation(self):
        for target in [
            Path("relative.json"),
            self.root / "wrong.txt",
            self.root / "absent" / "new.json",
        ]:
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.service.prepare("conversations", (1,), target)
        for ids in [(), (1, 1), (True,), tuple(range(1, 102))]:
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.service.prepare("conversations", ids, self.destination)
        protected = UserExportService(self.db, ProtectedPathPolicy((self.root,)))
        with self.assertRaises(ValueError):
            protected.prepare("conversations", (1,), self.destination)

    def test_provider_cannot_authorize_or_supply_destination(self):
        request, _ = self.prepared()
        validator = ActionRequestValidator(self.registry, self.policy)
        policy = ActionPermissionPolicy(self.policy)
        action = validator.validate(request)
        self.assertIs(
            policy.evaluate(action, ()), PermissionDecision.CONFIRMATION_REQUIRED
        )
        self.assertIs(
            policy.evaluate(action, (), confirmed=True), PermissionDecision.GRANTED
        )
        forged = replace(request, source="provider.gemini")
        self.assertIs(
            policy.evaluate(validator.validate(forged), (), confirmed=True),
            PermissionDecision.MISSING,
        )
        self.assertNotIn(str(self.destination), repr(request))

    def test_old_confirmation_cannot_authorize_new_owner(self):
        request, epoch = self.prepared()
        lease = self.leases.issue_confirmation(request, owner_epoch=epoch)
        self.leases.claim(
            ActionRequest(
                "new-action",
                "applications.launch",
                "chat",
                {"application_id": "spotify"},
            )
        )
        self.assertFalse(
            self.leases.consume_confirmation(lease, request, approved=True)
        )
        with self.assertRaises(ValueError):
            self.service.write(request, self.token)
