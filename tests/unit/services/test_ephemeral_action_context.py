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

    def test_resolves_natural_spotify_pronoun_controls(self) -> None:
        self.context.record_spotify_activity()

        cases = (
            (
                "Turn it up",
                "spotify.volume",
                {"service": "spotify", "volume_delta_percent": 10},
            ),
            (
                "Make it quieter",
                "spotify.volume",
                {"service": "spotify", "volume_delta_percent": -10},
            ),
            (
                "It's too loud",
                "spotify.volume",
                {"service": "spotify", "volume_delta_percent": -10},
            ),
            (
                "Turn it up by twenty percent",
                "spotify.volume",
                {"service": "spotify", "volume_delta_percent": 20},
            ),
            (
                "Make it quieter by ten percent",
                "spotify.volume",
                {"service": "spotify", "volume_delta_percent": -10},
            ),
            ("Skip this", "spotify.next", {"service": "spotify"}),
            ("I don't like this one", "spotify.next", {"service": "spotify"}),
            ("Go back", "spotify.previous", {"service": "spotify"}),
            ("Stop it", "spotify.pause", {"service": "spotify"}),
        )

        for text, action_id, parameters in cases:
            with self.subTest(text=text):
                request = self.context.resolve(text)

                self.assertEqual(request.action_id, action_id)
                self.assertEqual(dict(request.parameters), parameters)

    def test_ambiguous_spotify_phrases_need_recent_context(self) -> None:
        self.assertIsNone(self.context.resolve("I don't like this one"))
        self.assertIsNone(self.context.resolve("Go back"))

    def test_uses_recent_spotify_state_to_correct_noisy_transcripts(self) -> None:
        self.context.record_spotify_action("spotify.play")

        pause = self.context.resolve("Paue MIZIK!")

        self.assertEqual(pause.action_id, "spotify.pause")
        self.assertEqual(dict(pause.parameters), {"service": "spotify"})

        self.context.record_spotify_action("spotify.pause")
        resume = self.context.resolve("Continua la música")

        self.assertEqual(resume.action_id, "spotify.resume")
        self.assertEqual(dict(resume.parameters), {"service": "spotify"})

    def test_contextual_spotify_resolution_does_not_blindly_guess(self) -> None:
        self.context.record_spotify_action("spotify.pause")

        clarification = self.context.resolve("Pause or resume music")
        unrelated = self.context.resolve("I really enjoy music theory")
        unrelated_follow_up = self.context.resolve("Continue working on the project")

        self.assertIsInstance(clarification, EphemeralReferenceError)
        self.assertIn("pause", clarification.message)
        self.assertIn("resume", clarification.message)
        self.assertIsNone(unrelated)
        self.assertIsNone(unrelated_follow_up)

    def test_contextual_correction_requires_fresh_successful_activity(self) -> None:
        self.assertIsNone(self.context.resolve("Continua la música"))

        self.context.record_spotify_action("spotify.pause")
        self.now += 31.0

        self.assertIsNone(self.context.resolve("Continua la música"))

    def test_clearing_spotify_activity_removes_contextual_corrections(self) -> None:
        self.context.record_spotify_action("spotify.pause")
        self.context.clear_spotify_activity()

        self.assertIsNone(self.context.resolve("Continua la música"))

    def test_exposes_only_sanitized_fresh_intent_context(self) -> None:
        self.context.record_successful_action("spotify.pause")
        self.context.record_application("spotify")
        self.context.record_directory(r"C:\Users\Akiha\Music")

        snapshot = self.context.intent_context_snapshot()

        self.assertEqual(snapshot.recent_action_id, "spotify.pause")
        self.assertEqual(snapshot.recent_application_id, "spotify")
        self.assertEqual(snapshot.spotify_playback_state, "paused")
        self.assertTrue(snapshot.has_recent_spotify_activity)
        self.assertTrue(snapshot.has_recent_directory)
        self.assertNotIn(r"C:\Users\Akiha", snapshot.render_for_provider())

        self.now += 31.0
        expired = self.context.intent_context_snapshot()

        self.assertFalse(expired.has_action_context)

    def test_spotify_search_does_not_claim_playback_context(self) -> None:
        self.context.record_successful_action("spotify.search_tracks")

        snapshot = self.context.intent_context_snapshot()

        self.assertEqual(snapshot.recent_action_id, "spotify.search_tracks")
        self.assertFalse(snapshot.has_recent_spotify_activity)

    def test_non_spotify_action_survives_empty_spotify_context(self) -> None:
        self.context.record_successful_action("applications.launch")

        snapshot = self.context.intent_context_snapshot()

        self.assertEqual(snapshot.recent_action_id, "applications.launch")
        self.assertFalse(snapshot.has_recent_spotify_activity)

    def test_empty_context_snapshot_is_safe_before_any_action(self) -> None:
        self.assertFalse(self.context.intent_context_snapshot().has_action_context)

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
