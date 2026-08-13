"""Tests for hosted-live transcript acceptance and canonical persistence."""

from __future__ import annotations

import unittest

from project_akiha.app.chat_controller import CanonicalLiveChatCommit
from project_akiha.app.live_transcript_controller import LiveTranscriptController
from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.core.voice_session import (
    AssistantTextRevision,
    EndpointReason,
    TranscriptRevision,
    TranscriptStatus,
    VoiceInputMode,
    VoiceProcessingMode,
)
from project_akiha.providers.ai import ChatMessage


class LiveTranscriptControllerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.chat = _RecordingChatController()
        self.authority = _TranscriptAuthority()
        self.input_revisions: list[TranscriptRevision] = []
        self.assistant_revisions: list[AssistantTextRevision] = []
        self.controller = LiveTranscriptController(
            self.chat,
            self.authority,
            on_input_revision=self.input_revisions.append,
            on_assistant_revision=self.assistant_revisions.append,
        )
        self.controller.start_turn(session_id="session-1", turn_id="turn-1")

    async def test_partials_remain_ephemeral_until_both_finals_are_ready(self) -> None:
        self.assertTrue(self.controller.transcript_revised(_input(0, "Hello")))
        self.assertTrue(self.controller.assistant_text_revised(_assistant(0, "Good")))
        self.assertTrue(self.controller.turn_completed("turn-1"))

        self.assertIsNone(await self.controller.commit_completed_turn("turn-1"))
        self.assertEqual(self.chat.calls, [])

        self.assertTrue(
            self.controller.transcript_revised(_input(1, "Hello Akiha", is_final=True))
        )
        self.assertTrue(
            self.controller.assistant_text_revised(
                _assistant(1, "Good afternoon.", is_final=True)
            )
        )
        committed = await self.controller.commit_completed_turn("turn-1")

        self.assertIsNotNone(committed)
        self.assertEqual(
            self.chat.calls,
            [("Hello Akiha", "Good afternoon.")],
        )
        self.assertIsNone(await self.controller.commit_completed_turn("turn-1"))
        self.assertEqual(len(self.input_revisions), 2)
        self.assertEqual(len(self.assistant_revisions), 2)

    async def test_audio_only_commit_requires_explicit_permission(self) -> None:
        self.controller.transcript_revised(_input(0, "Hello", is_final=True))
        self.controller.turn_completed("turn-1")

        self.assertIsNone(await self.controller.commit_completed_turn("turn-1"))
        committed = await self.controller.commit_completed_turn(
            "turn-1",
            allow_audio_only=True,
        )

        self.assertIsNotNone(committed)
        self.assertEqual(self.chat.calls, [("Hello", None)])

    async def test_hosted_commit_can_defer_memory_processing(self) -> None:
        self.controller.transcript_revised(_input(0, "Hello", is_final=True))
        self.controller.assistant_text_revised(_assistant(0, "Hello.", is_final=True))
        self.controller.turn_completed("turn-1")

        committed = await self.controller.commit_completed_turn(
            "turn-1",
            process_memory=False,
        )

        self.assertIsNotNone(committed)
        self.assertEqual(self.chat.process_memory_values, [False])

    async def test_wrong_stale_and_post_final_revisions_are_rejected(self) -> None:
        self.assertFalse(
            self.controller.transcript_revised(
                _input(0, "Wrong", session_id="session-2")
            )
        )
        self.assertTrue(self.controller.transcript_revised(_input(1, "Newer")))
        self.assertFalse(self.controller.transcript_revised(_input(0, "Older")))
        self.assertTrue(
            self.controller.transcript_revised(_input(2, "Final", is_final=True))
        )
        self.assertFalse(self.controller.transcript_revised(_input(3, "Too late")))
        self.assertEqual(self.chat.calls, [])

    async def test_turn_authority_can_reject_a_well_formed_final(self) -> None:
        self.authority.allow = False

        accepted = self.controller.transcript_revised(
            _input(0, "Not authoritative", is_final=True)
        )

        self.assertFalse(accepted)
        snapshot = self.controller.snapshot
        assert snapshot is not None
        self.assertIsNone(snapshot.final_user_text)
        self.assertEqual(self.input_revisions, [])

    async def test_cancel_discards_transcripts_and_rejects_late_callbacks(self) -> None:
        self.controller.transcript_revised(_input(0, "Temporary"))

        self.assertTrue(self.controller.cancel_turn("turn-1"))
        self.assertFalse(
            self.controller.transcript_revised(_input(1, "Late", is_final=True))
        )
        self.assertIsNone(await self.controller.commit_completed_turn("turn-1"))
        self.assertEqual(self.chat.calls, [])

    async def test_new_turn_can_start_only_after_prior_commit(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "already active"):
            self.controller.start_turn(session_id="session-1", turn_id="turn-2")

        self.controller.transcript_revised(_input(0, "Hello", is_final=True))
        self.controller.assistant_text_revised(_assistant(0, "Hello.", is_final=True))
        self.controller.turn_completed("turn-1")
        await self.controller.commit_completed_turn("turn-1")

        self.controller.start_turn(session_id="session-1", turn_id="turn-2")
        snapshot = self.controller.snapshot
        assert snapshot is not None
        self.assertEqual(snapshot.turn_id, "turn-2")

    async def test_persistence_failure_is_terminal_and_never_retried(self) -> None:
        self.chat.fail = True
        self.controller.transcript_revised(_input(0, "Hello", is_final=True))
        self.controller.assistant_text_revised(_assistant(0, "Hello.", is_final=True))
        self.controller.turn_completed("turn-1")

        with self.assertRaisesRegex(RuntimeError, "storage failed"):
            await self.controller.commit_completed_turn("turn-1")

        self.chat.fail = False
        self.assertIsNone(await self.controller.commit_completed_turn("turn-1"))
        self.assertEqual(self.chat.calls, [("Hello", "Hello.")])
        snapshot = self.controller.snapshot
        assert snapshot is not None
        self.assertTrue(snapshot.commit_failed)

    async def test_voice_coordinator_is_the_real_input_authority(self) -> None:
        coordinator = VoiceSessionCoordinator(
            session_id_factory=lambda: "hosted-session"
        )
        coordinator.request_start(VoiceProcessingMode.HOSTED_LIVE)
        coordinator.activate()
        turn = coordinator.begin_turn(VoiceInputMode.HOSTED_LIVE_CONVERSATION)
        controller = LiveTranscriptController(self.chat, coordinator)
        controller.start_turn(session_id=turn.session_id, turn_id=turn.turn_id)
        revision = _input(
            0,
            "Canonical input",
            is_final=True,
            session_id=turn.session_id,
            turn_id=turn.turn_id,
        )

        self.assertTrue(controller.transcript_revised(revision))

        active_turn = coordinator.snapshot.active_turn
        assert active_turn is not None
        self.assertEqual(active_turn.accepted_final_transcript, revision)


class _RecordingChatController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.process_memory_values: list[bool] = []
        self.fail = False

    async def commit_canonical_live_turn(
        self,
        user_content: str,
        assistant_content: str | None,
        *,
        process_memory: bool = True,
    ) -> CanonicalLiveChatCommit:
        self.calls.append((user_content, assistant_content))
        self.process_memory_values.append(process_memory)
        if self.fail:
            raise RuntimeError("storage failed")
        return CanonicalLiveChatCommit(
            user_message=ChatMessage(role="user", content=user_content),
            assistant_message=(
                ChatMessage(role="assistant", content=assistant_content)
                if assistant_content is not None
                else None
            ),
        )


class _TranscriptAuthority:
    def __init__(self) -> None:
        self.allow = True
        self.revisions: list[TranscriptRevision] = []

    def accept_transcript_revision(self, revision: TranscriptRevision) -> bool:
        self.revisions.append(revision)
        return self.allow


def _input(
    revision: int,
    text: str,
    *,
    is_final: bool = False,
    session_id: str = "session-1",
    turn_id: str = "turn-1",
) -> TranscriptRevision:
    return TranscriptRevision(
        session_id=session_id,
        turn_id=turn_id,
        revision_number=revision,
        text=text,
        status=TranscriptStatus.FINAL if is_final else TranscriptStatus.PARTIAL,
        provider_name="gemini-live",
        endpoint_reason=EndpointReason.PROVIDER_FINAL if is_final else None,
    )


def _assistant(
    revision: int,
    text: str,
    *,
    is_final: bool = False,
) -> AssistantTextRevision:
    return AssistantTextRevision(
        session_id="session-1",
        turn_id="turn-1",
        revision_number=revision,
        text=text,
        is_final=is_final,
    )


if __name__ == "__main__":
    unittest.main()
