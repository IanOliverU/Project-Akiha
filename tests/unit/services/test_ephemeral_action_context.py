"""Tests for bounded, expiring assistant reference context."""

from __future__ import annotations

import unittest

from project_akiha.services.ephemeral_action_context import (
    EphemeralActionContext,
    EphemeralDirectoryReference,
    EphemeralReferenceError,
    EphemeralSelectionKind,
    EphemeralSelectionReference,
)


class EphemeralActionContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 100.0
        self.context = EphemeralActionContext(
            ttl_seconds=30.0,
            now=lambda: self.now,
        )

    def test_resolves_natural_numbered_reference_only_from_active_kind(self) -> None:
        self.context.record_selection(
            EphemeralSelectionKind.SPOTIFY_ALBUM,
            3,
            allowed_verbs=frozenset(("open", "play")),
        )

        reference = self.context.resolve("Akiha, please open the second one.")

        self.assertEqual(
            reference,
            EphemeralSelectionReference(
                EphemeralSelectionKind.SPOTIFY_ALBUM,
                "open",
                index=2,
            ),
        )

    def test_rejects_wrong_kind_verb_and_out_of_range_reference(self) -> None:
        self.context.record_selection(
            EphemeralSelectionKind.SPOTIFY_TRACK,
            2,
            allowed_verbs=frozenset(("play",)),
        )

        wrong_kind = self.context.resolve("Play album result 1")
        wrong_verb = self.context.resolve("Open the first one")
        out_of_range = self.context.resolve("Play result 3")

        self.assertIsInstance(wrong_kind, EphemeralReferenceError)
        self.assertIn("track", wrong_kind.message)
        self.assertIsInstance(wrong_verb, EphemeralReferenceError)
        self.assertIn("play", wrong_verb.message)
        self.assertIsInstance(out_of_range, EphemeralReferenceError)
        self.assertIn("1 to 2", out_of_range.message)

    def test_latest_result_set_replaces_previous_category(self) -> None:
        self.context.record_selection(
            EphemeralSelectionKind.SPOTIFY_ALBUM,
            2,
            allowed_verbs=frozenset(("play",)),
        )
        self.context.record_selection(
            EphemeralSelectionKind.DIRECTORY,
            4,
            allowed_verbs=frozenset(("open",)),
        )

        reference = self.context.resolve("Open result 3")

        self.assertEqual(
            reference,
            EphemeralSelectionReference(
                EphemeralSelectionKind.DIRECTORY,
                "open",
                index=3,
            ),
        )

    def test_selected_album_and_playlist_references_are_typed(self) -> None:
        self.context.record_selected(
            EphemeralSelectionKind.SPOTIFY_ALBUM,
            allowed_verbs=frozenset(("open", "play")),
        )

        reference = self.context.resolve("Would you please play that album for me?")
        mismatch = self.context.resolve("Play that playlist")

        self.assertEqual(
            reference,
            EphemeralSelectionReference(
                EphemeralSelectionKind.SPOTIFY_ALBUM,
                "play",
                selected=True,
            ),
        )
        self.assertIsInstance(mismatch, EphemeralReferenceError)

    def test_resolves_spotify_and_application_pronouns_to_typed_actions(self) -> None:
        self.context.record_spotify_activity()
        self.context.record_application("discord")

        pause = self.context.resolve("Pause it")
        close = self.context.resolve("Could you close the app for me?")

        self.assertEqual(pause.action_id, "spotify.pause")
        self.assertEqual(dict(pause.parameters), {"service": "spotify"})
        self.assertEqual(close.action_id, "applications.close")
        self.assertEqual(close.parameters["application_id"], "discord")

    def test_resolves_named_child_only_under_recent_directory(self) -> None:
        self.context.record_directory(r"C:\Users\Akiha\Downloads")

        reference = self.context.resolve("Open Compressed folder inside it")
        unnamed = self.context.resolve("Open the folder inside it")

        self.assertEqual(
            reference,
            EphemeralDirectoryReference(
                "Compressed",
                r"C:\Users\Akiha\Downloads",
            ),
        )
        self.assertIsInstance(unnamed, EphemeralReferenceError)
        self.assertIn("name the folder", unnamed.message)

    def test_context_expires_and_clear_discards_every_reference(self) -> None:
        self.context.record_selection(
            EphemeralSelectionKind.FILE,
            1,
            allowed_verbs=frozenset(("open", "play")),
        )
        self.context.record_directory(r"C:\Users\Akiha\Desktop")
        self.context.record_application("chrome")
        self.context.record_spotify_activity()
        self.now += 31.0

        self.assertIsInstance(
            self.context.resolve("Open the first one"),
            EphemeralReferenceError,
        )
        self.assertIsNone(self.context.current_directory)
        self.assertIsInstance(
            self.context.resolve("Close the app"),
            EphemeralReferenceError,
        )
        self.assertIsInstance(
            self.context.resolve("Pause it"),
            EphemeralReferenceError,
        )

        self.context.record_application("discord")
        self.context.clear()
        self.assertIsInstance(
            self.context.resolve("Close it"),
            EphemeralReferenceError,
        )

    def test_negated_reference_never_resolves(self) -> None:
        self.context.record_application("spotify")

        self.assertIsNone(self.context.resolve("Do not close the app"))

    def test_rejects_invalid_registration(self) -> None:
        with self.assertRaises(ValueError):
            self.context.record_selection(
                EphemeralSelectionKind.FILE,
                11,
                allowed_verbs=frozenset(("open",)),
            )
        with self.assertRaises(ValueError):
            self.context.record_application("powershell")


if __name__ == "__main__":
    unittest.main()
