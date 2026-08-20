"""Tests for immutable action contracts and the application registry."""

from __future__ import annotations

import unittest

from project_akiha.core.actions import (
    ActionFailureCategory,
    ActionRequest,
    ActionValidationError,
    ApprovedDirectory,
    build_default_action_registry,
)


class ActionModelsAndRegistryTest(unittest.TestCase):
    """Verify action proposals cannot alter application-owned definitions."""

    def test_request_copies_and_freezes_parameters(self) -> None:
        parameters: dict[str, object] = {"application_id": "spotify"}
        request = ActionRequest(
            correlation_id="request-1",
            action_id="applications.launch",
            source="chat",
            parameters=parameters,
        )

        parameters["application_id"] = "chrome"

        self.assertEqual(request.parameters["application_id"], "spotify")
        with self.assertRaises(TypeError):
            request.parameters["application_id"] = "discord"  # type: ignore[index]

    def test_default_registry_contains_only_allowlisted_actions(self) -> None:
        registry = build_default_action_registry()

        self.assertEqual(
            tuple(item.action_id for item in registry.definitions),
            (
                "files.search",
                "directories.search",
                "files.open_directory",
                "files.open",
                "applications.launch",
                "applications.close",
                "spotify.play",
                "spotify.pause",
                "spotify.resume",
                "spotify.next",
                "spotify.previous",
                "spotify.current_playback",
                "spotify.shuffle",
                "spotify.repeat",
                "spotify.volume",
                "spotify.seek",
                "spotify.search_artists",
                "spotify.open_artist",
                "spotify.play_artist",
                "spotify.search_tracks",
                "spotify.play_track",
                "spotify.search_albums",
                "spotify.open_album",
                "spotify.play_album",
                "spotify.search_playlists",
                "spotify.play_playlist",
                "spotify.play_favorites",
            ),
        )

    def test_unknown_action_is_rejected_with_safe_category(self) -> None:
        registry = build_default_action_registry()

        with self.assertRaises(ActionValidationError) as captured:
            registry.resolve("system.run")

        self.assertEqual(
            captured.exception.category,
            ActionFailureCategory.UNKNOWN_ACTION,
        )

    def test_request_rejects_audit_unsafe_identifiers(self) -> None:
        with self.assertRaises(ValueError):
            ActionRequest(
                correlation_id="request\n1",
                action_id="applications.launch",
                source="chat",
                parameters={"application_id": "spotify"},
            )
        with self.assertRaises(ValueError):
            ActionRequest(
                correlation_id="request-1",
                action_id="RUN THIS",
                source="chat",
                parameters={},
            )

    def test_approved_directory_derives_capabilities_from_permission_ids(self) -> None:
        directory = ApprovedDirectory(
            root=r"C:\Users\Akiha\Documents",
            search_permission_id=1,
            open_permission_id=None,
            is_available=True,
        )

        self.assertTrue(directory.can_search)
        self.assertFalse(directory.can_open)

        with self.assertRaises(ValueError):
            ApprovedDirectory(
                root=r"C:\Users\Akiha\Documents",
                search_permission_id=None,
                open_permission_id=None,
                is_available=True,
            )


if __name__ == "__main__":
    unittest.main()
