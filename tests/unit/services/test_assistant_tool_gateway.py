"""Tests for constrained LLM assistant-tool proposals."""

from __future__ import annotations

import unittest

from project_akiha.core.actions import DirectorySearchMatch, FileSearchMatch
from project_akiha.providers.ai import ChatMessage
from project_akiha.services.assistant_tool_gateway import (
    AssistantToolKind,
    AssistantToolProposal,
    AssistantToolProposalError,
    AssistantToolResultStore,
    LLMAssistantToolGateway,
    MediaKind,
    build_media_search_queries,
    directory_name_matches,
    filter_directory_matches,
    filter_media_matches,
    parse_assistant_tool_proposal,
    parse_directory_navigation_proposal,
    should_request_tool_proposal,
)


class AssistantToolProposalTest(unittest.IsolatedAsyncioTestCase):
    async def test_gateway_asks_provider_for_non_executable_proposal(self) -> None:
        provider = _FakeProvider(
            '{"action":"play_media","title":"Elis",'
            '"artist":"Megurine Luka","media_kind":"audio"}'
        )
        gateway = LLMAssistantToolGateway(provider, enabled=True)

        proposal = await gateway.propose("Play Elis by Megurine Luka")

        self.assertEqual(proposal.kind, AssistantToolKind.PLAY_MEDIA)
        self.assertEqual(proposal.title, "Elis")
        self.assertEqual(proposal.artist, "Megurine Luka")
        self.assertEqual(len(provider.messages), 2)
        self.assertNotIn("C:\\", provider.messages[0].content)

    async def test_disabled_gateway_never_calls_provider(self) -> None:
        provider = _FakeProvider(
            '{"action":"launch_application","application_id":"chrome"}'
        )
        gateway = LLMAssistantToolGateway(provider, enabled=False)

        proposal = await gateway.propose("Open Chrome")

        self.assertEqual(proposal.kind, AssistantToolKind.NONE)
        self.assertEqual(provider.messages, ())

    def test_rejects_unallowlisted_application_and_extra_path(self) -> None:
        with self.assertRaises(AssistantToolProposalError):
            parse_assistant_tool_proposal(
                '{"action":"launch_application","application_id":"powershell"}'
            )
        with self.assertRaises(AssistantToolProposalError):
            parse_assistant_tool_proposal(
                '{"action":"play_media","title":"Elis","artist":"",'
                '"media_kind":"audio","path":"C:\\\\secret"}'
            )

    def test_rejects_media_path_instead_of_search_terms(self) -> None:
        with self.assertRaises(AssistantToolProposalError):
            parse_assistant_tool_proposal(
                '{"action":"play_media","title":"C:\\\\secret.mp3",'
                '"artist":"","media_kind":"audio"}'
            )

    def test_accepts_fenced_json_but_not_prose(self) -> None:
        proposal = parse_assistant_tool_proposal(
            '```json\n{"action":"launch_application","application_id":"vscode"}\n```'
        )
        self.assertEqual(proposal.application_id, "vscode")
        with self.assertRaises(AssistantToolProposalError):
            parse_assistant_tool_proposal(
                'Certainly. {"action":"launch_application","application_id":"vscode"}'
            )

    def test_accepts_only_allowlisted_close_proposals(self) -> None:
        proposal = parse_assistant_tool_proposal(
            '{"action":"close_application","application_id":"vlc"}'
        )

        self.assertEqual(proposal.kind, AssistantToolKind.CLOSE_APPLICATION)
        self.assertEqual(proposal.application_id, "vlc")
        with self.assertRaises(AssistantToolProposalError):
            parse_assistant_tool_proposal(
                '{"action":"close_application","application_id":"akiha"}'
            )

    def test_accepts_path_free_directory_proposal(self) -> None:
        proposal = parse_assistant_tool_proposal(
            '{"action":"open_directory","name":"Compressed","parent":"Downloads"}'
        )

        self.assertEqual(proposal.kind, AssistantToolKind.OPEN_DIRECTORY)
        self.assertEqual(proposal.directory_name, "Compressed")
        self.assertEqual(proposal.parent_name, "Downloads")
        with self.assertRaises(AssistantToolProposalError):
            parse_assistant_tool_proposal(
                '{"action":"open_directory","name":"Compressed",'
                '"parent":"C:\\\\Users\\\\Akiha\\\\Downloads"}'
            )

    def test_likelihood_gate_limits_extra_provider_requests(self) -> None:
        self.assertTrue(
            should_request_tool_proposal("Akiha, play Elis by Megurine Luka")
        )
        self.assertTrue(should_request_tool_proposal("Akiha, close VLC"))
        self.assertTrue(should_request_tool_proposal("Discordを起動してください"))
        self.assertFalse(should_request_tool_proposal("What should we do today?"))


class AssistantToolMediaTest(unittest.TestCase):
    def test_filters_title_and_artist_in_any_filename_order(self) -> None:
        proposal = AssistantToolProposal(
            AssistantToolKind.PLAY_MEDIA,
            title="Elis",
            artist="Megurine Luka",
            media_kind=MediaKind.AUDIO,
        )
        matches = (
            _match(r"C:\Desktop\Solitude\Megurine Luka - Elis.mp3"),
            _match(r"C:\Desktop\Solitude\01 -ELIS-.flac"),
            _match(r"C:\Desktop\Solitude\Megurine Luka - Elis.mp4"),
        )

        filtered = filter_media_matches(matches, proposal)

        self.assertEqual(
            tuple(match.name for match in filtered),
            ("Megurine Luka - Elis.mp3",),
        )

    def test_tolerates_common_transcription_variants_locally(self) -> None:
        proposal = AssistantToolProposal(
            AssistantToolKind.PLAY_MEDIA,
            title="Alice",
            artist="Megorin Luka",
            media_kind=MediaKind.AUDIO,
        )

        filtered = filter_media_matches(
            (_match(r"C:\Desktop\Solitude\Megurine Luka - Elis.mp3"),),
            proposal,
        )

        self.assertEqual(
            tuple(match.name for match in filtered),
            ("Megurine Luka - Elis.mp3",),
        )
        self.assertIn("luka", build_media_search_queries(proposal))
        self.assertEqual(build_media_search_queries(proposal)[-1], ".")

    def test_result_store_resolves_only_explicit_valid_number(self) -> None:
        store = AssistantToolResultStore()
        match = _match(r"C:\Desktop\Solitude\Megurine Luka - Elis.mp3")
        store.replace((match,))

        request = store.parse_follow_up("Akiha, play result 1")

        self.assertIsNotNone(request)
        self.assertEqual(request.action_id, "files.open")
        self.assertEqual(request.source, "tool_followup")
        self.assertEqual(request.parameters["path"], match.path)
        self.assertIsNone(store.parse_follow_up("play result 2"))
        self.assertIsNone(store.parse_follow_up("play C:\\secret.mp3"))

    def test_result_store_rejects_non_media_match(self) -> None:
        store = AssistantToolResultStore()

        with self.assertRaises(ValueError):
            store.replace((_match(r"C:\Desktop\run.exe"),))


class AssistantDirectoryNavigationTest(unittest.TestCase):
    def test_parses_parent_and_temporary_context_requests(self) -> None:
        parent = parse_directory_navigation_proposal(
            "Open the Compressed folder inside Downloads",
            has_context=False,
        )
        contextual = parse_directory_navigation_proposal(
            "I heard you say: Okay, Akiha, now open Compressed",
            has_context=True,
        )
        spoken_contextual = parse_directory_navigation_proposal(
            "Open Compressed Directory",
            has_context=True,
        )
        parent_suggestion = parse_directory_navigation_proposal(
            "How about the compressed directory inside Downloads?",
            has_context=False,
        )
        corrected_contextual = parse_directory_navigation_proposal(
            "Compressed down, I mean compressed, open compressed directory.",
            has_context=True,
        )

        self.assertIsNotNone(parent)
        self.assertEqual(parent.directory_name, "Compressed")
        self.assertEqual(parent.parent_name, "Downloads")
        self.assertIsNotNone(contextual)
        self.assertEqual(contextual.directory_name, "Compressed")
        self.assertEqual(contextual.parent_name, "")
        self.assertIsNotNone(spoken_contextual)
        self.assertEqual(spoken_contextual.directory_name, "Compressed")
        self.assertEqual(spoken_contextual.parent_name, "")
        self.assertIsNotNone(parent_suggestion)
        self.assertEqual(parent_suggestion.directory_name, "compressed")
        self.assertEqual(parent_suggestion.parent_name, "Downloads")
        self.assertIsNotNone(corrected_contextual)
        self.assertEqual(corrected_contextual.directory_name, "compressed")
        self.assertEqual(corrected_contextual.parent_name, "")
        self.assertIsNone(
            parse_directory_navigation_proposal(
                "Now open Compressed",
                has_context=False,
            )
        )
        self.assertIsNone(
            parse_directory_navigation_proposal(
                "Do not open Compressed Directory",
                has_context=True,
            )
        )

    def test_filters_fuzzy_directory_names_and_matches_parent_alias(self) -> None:
        proposal = AssistantToolProposal(
            AssistantToolKind.OPEN_DIRECTORY,
            directory_name="Compress",
            parent_name="Download",
        )
        match = DirectorySearchMatch(
            name="Compressed",
            path=r"C:\Users\Akiha\Downloads\Compressed",
            modified_at="2026-07-31T00:00:00+00:00",
        )

        self.assertEqual(filter_directory_matches((match,), proposal), (match,))
        self.assertTrue(directory_name_matches("Download", "Downloads"))

    def test_result_store_opens_only_selected_directory_result(self) -> None:
        store = AssistantToolResultStore()
        match = DirectorySearchMatch(
            name="Compressed",
            path=r"C:\Users\Akiha\Downloads\Compressed",
            modified_at="2026-07-31T00:00:00+00:00",
        )
        store.replace_directories((match,))

        request = store.parse_follow_up("Open result 1")

        self.assertIsNotNone(request)
        self.assertEqual(request.action_id, "files.open_directory")
        self.assertEqual(request.parameters["path"], match.path)
        self.assertIsNone(store.parse_follow_up("Play result 1"))


class _FakeProvider:
    def __init__(self, response: str) -> None:
        self._response = response
        self.messages: tuple[ChatMessage, ...] = ()

    async def generate_response(self, messages) -> str:
        self.messages = tuple(messages)
        return self._response


def _match(path: str) -> FileSearchMatch:
    return FileSearchMatch(
        name=path.rsplit("\\", 1)[-1],
        path=path,
        size_bytes=10,
        modified_at="2026-07-31T00:00:00+00:00",
    )


if __name__ == "__main__":
    unittest.main()
