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

    def test_parses_open_file_command_with_explicit_prefix(self) -> None:
        request = self.parser.parse(
            r"/open-file C:\Users\Akiha\Documents\notes.txt",
            correlation_id="chat-4",
        )

        self.assertIsNotNone(request)
        self.assertEqual(request.action_id, "files.open")
        self.assertEqual(
            request.parameters["path"],
            r"C:\Users\Akiha\Documents\notes.txt",
        )

    def test_parses_allowlisted_application_command(self) -> None:
        request = self.parser.parse(
            "launch app: Chrome",
            correlation_id="chat-5",
        )

        self.assertIsNotNone(request)
        self.assertEqual(request.action_id, "applications.launch")
        self.assertEqual(request.parameters["application_id"], "chrome")

    def test_parses_spoken_application_aliases(self) -> None:
        cases = (
            ("Hello Akiha, can you open Discord application?", "discord"),
            ("Please open this code application.", "vscode"),
            ("Would you start Google Chrome?", "chrome"),
            ("Okay, can you open discord application?", "discord"),
            ("Akia, can you open discord application?", "discord"),
            ("Aka'ya! Open Visual Studio Code", "vscode"),
            ("Okay, huh? Open visuals to the code", "vscode"),
        )

        for text, application_id in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "applications.launch")
                self.assertEqual(request.parameters["application_id"], application_id)

    def test_parses_graceful_application_close_commands(self) -> None:
        cases = (
            ("close app: vlc", "vlc"),
            ("Akiha, close VLC", "vlc"),
            ("Please quit Spotify application.", "spotify"),
            ("Could you close Visual Studio Code?", "vscode"),
        )

        for text, application_id in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "applications.close")
                self.assertEqual(request.parameters["application_id"], application_id)

    def test_parses_typed_and_spoken_spotify_playback_commands(self) -> None:
        cases = (
            ("/spotify-play", "spotify.play"),
            ("Akiha, play Spotify.", "spotify.play"),
            ("Please pause the music", "spotify.pause"),
            ("Can you pause, Spotify?", "spotify.pause"),
            ("pause, Spotify", "spotify.pause"),
            ("Akia, POS, Spotify.", "spotify.pause"),
            ("Akia ha Puzz Spatify", "spotify.pause"),
            (
                "I heard you say: Akiha, could you please pause the song?",
                "spotify.pause",
            ),
            ("Continue Spotify playback", "spotify.resume"),
            ("Okay, next track", "spotify.next"),
            ("Akiha, go back to the previous song", "spotify.previous"),
        )

        for text, action_id in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, action_id)
                self.assertEqual(dict(request.parameters), {"service": "spotify"})

    def test_song_title_does_not_become_generic_spotify_control(self) -> None:
        self.assertIsNone(self.parser.parse("Play Elis by Megurine Luka"))
        self.assertIsNone(self.parser.parse("Can you pause, the meeting?"))

    def test_parses_explicit_spotify_artist_catalog_commands(self) -> None:
        cases = (
            "/spotify-artist Megurine Luka",
            "Play songs by Megurine Luka",
            "Please play music from Megurine Luka on Spotify.",
            "Akiha, listen to artist Megurine Luka.",
            "Play Megurine Luka's catalog on Spotify",
        )

        for text in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.play_artist")
                self.assertEqual(request.parameters["service"], "spotify")
                self.assertEqual(request.parameters["artist_query"], "Megurine Luka")

    def test_parses_standalone_spotify_artist_search_commands(self) -> None:
        cases = (
            "/spotify-search-artists Megurine Luka",
            "Search Spotify artists for Megurine Luka",
            "Please find artist Megurine Luka on Spotify.",
            "Akiha, search for Megurine Luka on Spotify",
            "Look up Spotify for the artist Megurine Luka",
        )

        for text in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.search_artists")
                self.assertEqual(
                    dict(request.parameters),
                    {
                        "service": "spotify",
                        "artist_query": "Megurine Luka",
                    },
                )

    def test_start_spotify_remains_an_application_launch(self) -> None:
        request = self.parser.parse("Start Spotify")

        self.assertIsNotNone(request)
        self.assertEqual(request.action_id, "applications.launch")

    def test_parses_spoken_directory_path(self) -> None:
        request = self.parser.parse(
            r"Akiha, please open the folder C:\Users\Akiha\Project Files."
        )

        self.assertIsNotNone(request)
        self.assertEqual(request.action_id, "files.open_directory")
        self.assertEqual(request.parameters["path"], r"C:\Users\Akiha\Project Files")

    def test_parses_approved_directory_alias(self) -> None:
        parser = AssistantActionRequestParser(
            {
                "akiha": r"C:\Users\MY PC\Desktop\AKIHA",
                "downloads": r"C:\Users\MY PC\Downloads",
            }
        )

        request = parser.parse("I heard you say: Akiha, open Akiha Directory")
        natural_request = parser.parse("I want you to open Downloads directly.")
        filled_request = parser.parse(
            "Okay, so for now, please open Downloads Directory."
        )

        self.assertIsNotNone(request)
        self.assertEqual(request.action_id, "files.open_directory")
        self.assertEqual(request.parameters["path"], r"C:\Users\MY PC\Desktop\AKIHA")
        self.assertIsNotNone(natural_request)
        self.assertEqual(natural_request.action_id, "files.open_directory")
        self.assertEqual(
            natural_request.parameters["path"],
            r"C:\Users\MY PC\Downloads",
        )
        self.assertIsNotNone(filled_request)
        self.assertEqual(
            filled_request.parameters["path"],
            r"C:\Users\MY PC\Downloads",
        )

    def test_unapproved_directory_alias_does_not_become_an_action(self) -> None:
        self.assertIsNone(self.parser.parse("Open Akiha Directory"))

    def test_ordinary_conversation_does_not_become_an_action(self) -> None:
        self.assertIsNone(self.parser.parse("Could you open the directory later?"))
        self.assertIsNone(self.parser.parse("Could you open this file later?"))
        self.assertIsNone(self.parser.parse("Could you open Chrome later?"))
        self.assertIsNone(self.parser.parse("How about Akiha Directory?"))
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
