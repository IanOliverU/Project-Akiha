"""Tests for scoped assistant-action permission decisions."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.actions import (
    ActionPermissionPolicy,
    ActionRequest,
    ActionRequestValidator,
    PermissionDecision,
    PermissionGrant,
    ProtectedPathPolicy,
    build_default_action_registry,
)


class ActionPermissionPolicyTest(unittest.TestCase):
    """Verify grants match both capability and normalized target scope."""

    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)
        self.approved_root = self.root / "Documents"
        self.approved_root.mkdir()
        self.outside_root = self.root / "Outside"
        self.outside_root.mkdir()
        self.path_policy = ProtectedPathPolicy()
        self.validator = ActionRequestValidator(
            build_default_action_registry(),
            self.path_policy,
        )
        self.policy = ActionPermissionPolicy(self.path_policy)

    def test_file_grant_covers_descendants_but_not_other_roots(self) -> None:
        child = self.approved_root / "Projects"
        child.mkdir()
        grant = self._grant("files.search", str(self.approved_root))

        allowed = self._validate(
            "files.search",
            {"root": str(child), "query": "akiha"},
        )
        outside = self._validate(
            "files.search",
            {"root": str(self.outside_root), "query": "akiha"},
        )

        self.assertEqual(
            self.policy.evaluate(allowed, (grant,)),
            PermissionDecision.GRANTED,
        )
        self.assertEqual(
            self.policy.evaluate(outside, (grant,)),
            PermissionDecision.MISSING,
        )

    def test_wrong_capability_and_revoked_grant_do_not_authorize(self) -> None:
        action = self._validate(
            "files.search",
            {"root": str(self.approved_root), "query": "akiha"},
        )
        wrong = self._grant("files.open", str(self.approved_root))
        revoked = PermissionGrant(
            id=2,
            capability="files.search",
            target=str(self.approved_root.resolve()),
            created_at="2026-07-30T12:00:00+00:00",
            revoked_at="2026-07-30T12:01:00+00:00",
        )

        self.assertEqual(
            self.policy.evaluate(action, (wrong, revoked)),
            PermissionDecision.MISSING,
        )

    def test_open_file_requires_confirmation_after_scope_grant(self) -> None:
        file_path = self.approved_root / "notes.txt"
        file_path.write_text("notes", encoding="utf-8")
        action = self._validate("files.open", {"path": str(file_path)})
        grant = self._grant("files.open", str(self.approved_root))

        self.assertEqual(
            self.policy.evaluate(action, (grant,)),
            PermissionDecision.CONFIRMATION_REQUIRED,
        )
        self.assertEqual(
            self.policy.evaluate(action, (grant,), confirmed=True),
            PermissionDecision.GRANTED,
        )

    def test_application_grant_matches_exact_catalog_identifier(self) -> None:
        action = self._validate(
            "applications.launch",
            {"application_id": "spotify"},
        )

        self.assertEqual(
            self.policy.evaluate(
                action,
                (self._grant("applications.launch", "spotify"),),
            ),
            PermissionDecision.GRANTED,
        )
        self.assertEqual(
            self.policy.evaluate(
                action,
                (self._grant("applications.launch", "chrome"),),
            ),
            PermissionDecision.MISSING,
        )

    def test_close_permission_is_separate_from_launch_permission(self) -> None:
        action = self._validate(
            "applications.close",
            {"application_id": "vlc"},
        )

        self.assertEqual(
            self.policy.evaluate(
                action,
                (self._grant("applications.launch", "vlc"),),
            ),
            PermissionDecision.MISSING,
        )
        self.assertEqual(
            self.policy.evaluate(
                action,
                (self._grant("applications.close", "vlc"),),
            ),
            PermissionDecision.GRANTED,
        )

    def test_spotify_playback_requires_its_exact_separate_grant(self) -> None:
        action = self._validate("spotify.pause", {"service": "spotify"})

        self.assertEqual(
            self.policy.evaluate(
                action,
                (self._grant("applications.launch", "spotify"),),
            ),
            PermissionDecision.MISSING,
        )
        self.assertEqual(
            self.policy.evaluate(
                action,
                (self._grant("spotify.playback", "spotify"),),
            ),
            PermissionDecision.GRANTED,
        )

    def _validate(
        self,
        action_id: str,
        parameters: dict[str, object],
    ):
        return self.validator.validate(
            ActionRequest(
                correlation_id="request-1",
                action_id=action_id,
                source="chat",
                parameters=parameters,
            )
        )

    @staticmethod
    def _grant(capability: str, target: str) -> PermissionGrant:
        return PermissionGrant(
            id=1,
            capability=capability,
            target=target,
            created_at="2026-07-30T12:00:00+00:00",
        )


if __name__ == "__main__":
    unittest.main()
