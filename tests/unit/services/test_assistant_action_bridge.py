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

    def test_parses_app_command_inside_natural_courtesy_envelope(self) -> None:
        cases = (
            "Akiha, could you please open Spotify for me?",
            "Would you mind opening the Spotify application?",
            "Would it be possible for you to just open Spotify right now?",
            "I'd like you to open Spotify, please.",
            "Can you open VLC for me, Akiha?",
            "Please open Discord, Akiha.",
            "Akiha, would you be able to open Visual Studio Code for me?",
        )

        expected_applications = (
            "spotify",
            "spotify",
            "spotify",
            "spotify",
            "vlc",
            "discord",
            "vscode",
        )
        for text, application_id in zip(cases, expected_applications, strict=True):
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

    def test_parses_spotify_control_inside_natural_courtesy_envelope(self) -> None:
        cases = (
            ("Akiha, could you please pause Spotify for me?", "spotify.pause"),
            ("Would you mind resuming the music?", "spotify.resume"),
            ("I'd like you to skip the next track, please.", "spotify.next"),
        )

        for text, action_id in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, action_id)

    def test_song_title_does_not_become_generic_spotify_control(self) -> None:
        self.assertIsNone(self.parser.parse("Play Elis by Megurine Luka"))
        self.assertIsNone(self.parser.parse("Can you pause, the meeting?"))

    def test_guarded_command_discussion_never_becomes_an_action(self) -> None:
        cases = (
            "Akiha, do not open Spotify.",
            "Could you please not pause Spotify?",
            "Tell me how to open Spotify.",
            "Why did you open Discord?",
            "If I asked you to open Chrome, what would happen?",
            'The phrase "open Spotify" is one of your commands.',
        )

        for text in cases:
            with self.subTest(text=text):
                self.assertIsNone(self.parser.parse(text))

    def test_negation_inside_spotify_title_remains_playable(self) -> None:
        request = self.parser.parse("Play Don't Start Now by Dua Lipa on Spotify.")

        self.assertIsNotNone(request)
        self.assertEqual(request.action_id, "spotify.play_track")
        self.assertEqual(request.parameters["track_query"], "Don't Start Now")
        self.assertEqual(request.parameters["artist_query"], "Dua Lipa")

    def test_parses_explicit_spotify_shuffle_states(self) -> None:
        cases = (
            ("Enable shuffle", True),
            ("Disable Shuffle", False),
            ("Akiha, turn Spotify shuffle on.", True),
            ("Please turn off shuffle", False),
            ("Switch shuffle off on Spotify", False),
            ("/spotify-shuffle on", True),
        )

        for text, enabled in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.shuffle")
                self.assertEqual(
                    dict(request.parameters),
                    {"service": "spotify", "enabled": enabled},
                )

    def test_parses_explicit_spotify_repeat_modes(self) -> None:
        cases = (
            ("Repeat this song", "track"),
            ("Akiha, repeat the current track.", "track"),
            ("Repeat this album", "context"),
            ("Please repeat the playlist on Spotify", "context"),
            ("Disable repeat", "off"),
            ("Turn Spotify repeat off", "off"),
            ("Please turn off repeat", "off"),
            ("/spotify-repeat context", "context"),
        )

        for text, mode in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.repeat")
                self.assertEqual(
                    dict(request.parameters),
                    {"service": "spotify", "mode": mode},
                )

    def test_ambiguous_repeat_enable_is_not_an_action(self) -> None:
        self.assertIsNone(self.parser.parse("Enable repeat"))

    def test_parses_bounded_spotify_volume_commands(self) -> None:
        cases = (
            ("Set Spotify volume to 50 percent", 50),
            ("Akiha, Spotify volume 25%", 25),
            ("Please set the volume to seventy five percent on Spotify", 75),
            ("Change Spotify volume level to one hundred percent", 100),
            ("Mute Spotify", 0),
            ("Increase Spotify volume to 50%", 50),
            ("Please raise music volume to sixty percent, Akiha.", 60),
            ("Could you lower playback volume to 35 percent for me?", 35),
            ("Turn Spotify volume up to eighty percent", 80),
            ("/spotify-volume 42", 42),
        )

        for text, volume_percent in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.volume")
                self.assertEqual(
                    dict(request.parameters),
                    {
                        "service": "spotify",
                        "volume_percent": volume_percent,
                    },
                )

    def test_generic_volume_command_is_not_hijacked(self) -> None:
        self.assertIsNone(self.parser.parse("Set volume to 50 percent"))

    def test_parses_state_aware_relative_spotify_volume_commands(self) -> None:
        cases = (
            ("Increase Spotify volume by 10%", 10),
            ("Please lower music volume by twenty percent, Akiha.", -20),
            ("Could you turn Spotify volume up by 15% for me?", 15),
            ("Turn down playback volume by five percent", -5),
            ("Raise the volume by 25% on Spotify", 25),
            ("Reduce the volume by thirty percent on Spotify", -30),
        )

        for text, volume_delta_percent in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.volume")
                self.assertEqual(
                    dict(request.parameters),
                    {
                        "service": "spotify",
                        "volume_delta_percent": volume_delta_percent,
                    },
                )

    def test_rejects_ambiguous_or_invalid_relative_volume_commands(self) -> None:
        cases = (
            "Increase volume by 10%",
            "Lower volume by ten percent",
            "Increase Spotify volume by 0%",
            "Increase Spotify volume by 101%",
            "Increase Spotify volume sometime",
        )

        for text in cases:
            with self.subTest(text=text):
                self.assertIsNone(self.parser.parse(text))

    def test_natural_envelopes_cover_every_spotify_action_family(self) -> None:
        cases = (
            ("Could you play Spotify music for me, Akiha?", "spotify.play"),
            ("Please pause my Spotify music, Akiha.", "spotify.pause"),
            ("Would you resume my Spotify playback for me?", "spotify.resume"),
            ("Could you skip the next track for me, Akiha?", "spotify.next"),
            ("Please go back to the previous song, Akiha.", "spotify.previous"),
            ("Could you enable Spotify shuffle for me?", "spotify.shuffle"),
            ("Please repeat the current track, Akiha.", "spotify.repeat"),
            ("Could you set Spotify volume to 45% for me?", "spotify.volume"),
            ("Please seek Spotify to 1:15, Akiha.", "spotify.seek"),
            (
                "Could you search Spotify artists for ADO for me?",
                "spotify.search_artists",
            ),
            ("Please open artist ADO on Spotify, Akiha.", "spotify.open_artist"),
            ("Could you play songs by ADO for me, Akiha?", "spotify.play_artist"),
            (
                "Please find song Usseewa by ADO on Spotify, Akiha.",
                "spotify.search_tracks",
            ),
            ("Could you play Usseewa by ADO on Spotify for me?", "spotify.play_track"),
            (
                "Please find album Kyougen by ADO on Spotify, Akiha.",
                "spotify.search_albums",
            ),
            (
                "Could you open album Kyougen by ADO on Spotify for me?",
                "spotify.open_album",
            ),
            (
                "Please play album Kyougen by ADO on Spotify, Akiha.",
                "spotify.play_album",
            ),
            (
                "Could you find playlist Night Drive on Spotify for me?",
                "spotify.search_playlists",
            ),
            (
                "Please play playlist Night Drive on Spotify, Akiha.",
                "spotify.play_playlist",
            ),
            (
                "Could you play my Spotify favorites for me, Akiha?",
                "spotify.play_favorites",
            ),
        )

        for text, action_id in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, action_id)

    def test_natural_wrappers_never_bypass_command_guards(self) -> None:
        cases = (
            "Please do not open Discord for me, Akiha.",
            "Could you please not pause Spotify, Akiha?",
            "Akiha, tell me how to enable shuffle on Spotify.",
            "Please remind me to open VLC later, Akiha.",
            'Could you repeat the phrase "open Spotify" for me, Akiha?',
        )

        for text in cases:
            with self.subTest(text=text):
                self.assertIsNone(self.parser.parse(text))

    def test_parses_absolute_spotify_seek_commands(self) -> None:
        cases = (
            ("Seek Spotify to 1 minute 30 seconds", 90),
            ("Akiha, Spotify seek to 2:15", 135),
            ("Please go to 1:02:03 on Spotify", 3723),
            ("Jump to thirty seconds on Spotify", 30),
            ("Restart current Spotify track", 0),
            ("Restart the current song on Spotify", 0),
            ("/spotify-seek 90", 90),
        )

        for text, position_seconds in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.seek")
                self.assertEqual(
                    dict(request.parameters),
                    {
                        "service": "spotify",
                        "position_seconds": position_seconds,
                    },
                )

    def test_invalid_or_generic_seek_is_not_dispatched(self) -> None:
        self.assertIsNone(self.parser.parse("Go to 1:75 on Spotify"))
        self.assertIsNone(self.parser.parse("Go to 2:15"))
        self.assertIsNone(self.parser.parse("Skip ahead 30 seconds"))

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

    def test_parses_explicit_spotify_artist_page_commands(self) -> None:
        cases = (
            "/spotify-open-artist ADO",
            "Open artist ADO on Spotify",
            "Please view the Spotify artist ADO.",
            "Akiha, show me artist ADO on Spotify",
            "Take me to artist ADO on Spotify",
            "Go to ADO's Spotify page",
        )

        for text in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.open_artist")
                self.assertEqual(
                    dict(request.parameters),
                    {"service": "spotify", "artist_query": "ADO"},
                )

    def test_parses_standalone_spotify_track_search_commands(self) -> None:
        cases = (
            "/spotify-search-tracks Usseewa | ADO",
            "Search Spotify tracks for Usseewa by ADO",
            "Please find song Usseewa by ADO on Spotify.",
            "Akiha, search for track Usseewa by ADO on Spotify",
        )

        for text in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.search_tracks")
                self.assertEqual(
                    dict(request.parameters),
                    {
                        "service": "spotify",
                        "track_query": "Usseewa",
                        "artist_query": "ADO",
                    },
                )

    def test_parses_spotify_album_search_commands(self) -> None:
        cases = (
            "/spotify-search-albums Kyougen | ADO",
            "Search Spotify albums for Kyougen by ADO",
            "Please find album Kyougen by ADO on Spotify.",
        )

        for text in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.search_albums")
                self.assertEqual(
                    dict(request.parameters),
                    {
                        "service": "spotify",
                        "album_query": "Kyougen",
                        "artist_query": "ADO",
                    },
                )

    def test_parses_spotify_playlist_search_commands(self) -> None:
        cases = (
            "/spotify-search-playlists Night Drive",
            "Search Spotify playlists for Night Drive",
            "Please find playlist named Night Drive on Spotify.",
            "Look up Spotify for the playlist Night Drive",
        )

        for text in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.search_playlists")
                self.assertEqual(
                    dict(request.parameters),
                    {"service": "spotify", "playlist_query": "Night Drive"},
                )

    def test_parses_spotify_playlist_playback_commands(self) -> None:
        cases = (
            "/spotify-playlist Night Drive",
            "Play Spotify playlist Night Drive",
            "Please play my playlist called Night Drive on Spotify.",
            "Play Night Drive playlist on Spotify",
        )

        for text in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.play_playlist")
                self.assertEqual(
                    dict(request.parameters),
                    {"service": "spotify", "playlist_query": "Night Drive"},
                )

    def test_playlist_result_reference_does_not_become_catalog_query(self) -> None:
        self.assertIsNone(self.parser.parse("Play playlist result 1"))

    def test_parses_spotify_liked_and_favorite_music_commands(self) -> None:
        cases = (
            ("Play my liked songs", "liked"),
            ("Please play my Spotify liked music.", "liked"),
            ("/spotify-liked", "liked"),
            ("Play my favorite music", "mix"),
            ("Play something I like on Spotify", "mix"),
            ("Play me something I like", "mix"),
            ("Akiha, can you play my Spotify favorites?", "mix"),
            ("/spotify-favorites", "mix"),
        )

        for text, mode in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.play_favorites")
                self.assertEqual(
                    dict(request.parameters),
                    {"service": "spotify", "favorite_mode": mode},
                )

    def test_parses_spotify_album_open_commands(self) -> None:
        cases = (
            "/spotify-open-album Kyougen | ADO",
            "Open Spotify album Kyougen by ADO",
            "Go to Kyougen album on Spotify",
        )

        for text in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.open_album")
                self.assertEqual(request.parameters["album_query"], "Kyougen")

    def test_parses_spotify_album_play_commands_before_generic_track(self) -> None:
        cases = (
            "/spotify-album Kyougen | ADO",
            "Play Spotify album Kyougen by ADO",
            "Please play album Kyougen by ADO on Spotify.",
            "Play Kyougen album on Spotify",
        )

        for text in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.play_album")
                self.assertEqual(request.parameters["album_query"], "Kyougen")

    def test_parses_explicit_spotify_track_playback_commands(self) -> None:
        cases = (
            "/spotify-track Usseewa | ADO",
            "Play Spotify track Usseewa by ADO",
            "Please play song Usseewa by ADO on Spotify.",
            "Akiha, play Usseewa by ADO on Spotify",
            "Listen to the Spotify song Usseewa by ADO",
        )

        for text in cases:
            with self.subTest(text=text):
                request = self.parser.parse(text)

                self.assertIsNotNone(request)
                self.assertEqual(request.action_id, "spotify.play_track")
                self.assertEqual(
                    dict(request.parameters),
                    {
                        "service": "spotify",
                        "track_query": "Usseewa",
                        "artist_query": "ADO",
                    },
                )

    def test_normalizes_spoken_spotify_alias_for_track_search(self) -> None:
        request = self.parser.parse("Find song USEWA BEADO on Swatifi")

        self.assertIsNotNone(request)
        self.assertEqual(request.action_id, "spotify.search_tracks")
        self.assertEqual(request.parameters["track_query"], "USEWA BEADO")

    def test_numbered_result_references_never_become_catalog_queries(self) -> None:
        cases = (
            "Play album result 11",
            "Open album result 11",
            "Play track result 11",
            "Play artist result 11",
            "Open artist result 11",
        )

        for text in cases:
            with self.subTest(text=text):
                self.assertIsNone(self.parser.parse(text))

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
