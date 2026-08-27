"""Tests for staged animation playback without artwork dependencies."""

from __future__ import annotations

import unittest
from pathlib import Path

from project_akiha.app.animation_playback_controller import (
    AnimationPlaybackController,
)
from project_akiha.core.state.animation import (
    AnimationClipId,
    AnimationSequenceId,
    AnimationState,
)
from project_akiha.providers.animation import (
    AnimationFrame,
    AnimationSequence,
)


class AnimationPlaybackControllerTest(unittest.TestCase):
    """Verify staged clips remain subordinate to semantic state authority."""

    def test_legacy_provider_uses_state_relative_clock(self) -> None:
        controller = AnimationPlaybackController(_LegacyProvider())
        controller.advance_tick()
        controller.advance_tick()

        controller.start_state(AnimationState.WALKING)

        self.assertEqual(controller.frame_number, 0)
        self.assertEqual(controller.frame().frame_index, 0)
        self.assertFalse(controller.staged_sleep_available)

    def test_sleep_start_advances_to_repeatable_loop(self) -> None:
        controller = AnimationPlaybackController(_SequenceProvider())

        controller.start_state(AnimationState.SLEEPING)
        completion = controller.advance_tick()

        self.assertIsNone(completion)
        self.assertEqual(controller.active_clip_id, AnimationClipId.SLEEP_LOOP)
        self.assertEqual(controller.frame_number, 0)
        self.assertEqual(controller.frame().image_path, Path("sleep-loop.png"))

    def test_wake_sequence_reports_completion_once(self) -> None:
        controller = AnimationPlaybackController(_SequenceProvider())
        controller.start_state(AnimationState.WAKING)

        completions = tuple(controller.advance_tick() for _ in range(6))

        completed = tuple(item for item in completions if item is not None)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].sequence_id, AnimationSequenceId.WAKE)
        self.assertEqual(completed[0].fallback_state, AnimationState.IDLE)
        self.assertEqual(controller.active_clip_id, AnimationClipId.GETTING_UP)
        self.assertIsNone(controller.advance_tick())

    def test_complete_sleep_and_wake_sequences_enable_staged_capability(self) -> None:
        controller = AnimationPlaybackController(_SequenceProvider())

        self.assertTrue(controller.staged_sleep_available)


class _LegacyProvider:
    def available_states(self) -> frozenset[AnimationState]:
        return frozenset(AnimationState)

    def frame_for(self, state: AnimationState, frame_number: int) -> AnimationFrame:
        return AnimationFrame(state=state, frame_index=frame_number)


class _SequenceProvider(_LegacyProvider):
    _sequences = {
        AnimationSequenceId.SLEEP: AnimationSequence(
            sequence_id=AnimationSequenceId.SLEEP,
            state=AnimationState.SLEEPING,
            clip_ids=(AnimationClipId.SLEEP_START, AnimationClipId.SLEEP_LOOP),
            fallback_state=AnimationState.IDLE,
            interruptible=True,
        ),
        AnimationSequenceId.WAKE: AnimationSequence(
            sequence_id=AnimationSequenceId.WAKE,
            state=AnimationState.WAKING,
            clip_ids=(
                AnimationClipId.WAKE_START,
                AnimationClipId.HALF_AWAKE,
                AnimationClipId.SITTING_ON_FUTON,
                AnimationClipId.GETTING_UP,
            ),
            fallback_state=AnimationState.IDLE,
            interruptible=True,
        ),
    }
    _loops = {AnimationClipId.SLEEP_LOOP}

    def available_sequences(self) -> frozenset[AnimationSequenceId]:
        return frozenset(self._sequences)

    def sequence_for(self, sequence_id: AnimationSequenceId) -> AnimationSequence:
        return self._sequences[sequence_id]

    def frame_for_clip(
        self,
        clip_id: AnimationClipId,
        frame_number: int,
    ) -> AnimationFrame:
        return AnimationFrame(
            state=self._state_for_clip(clip_id),
            frame_index=frame_number,
            image_path=Path(f"{clip_id.value.replace('_', '-')}.png"),
        )

    def clip_duration_ticks(self, clip_id: AnimationClipId) -> int:
        del clip_id
        return 1

    def clip_loops(self, clip_id: AnimationClipId) -> bool:
        return clip_id in self._loops

    @staticmethod
    def _state_for_clip(clip_id: AnimationClipId) -> AnimationState:
        if clip_id in {AnimationClipId.SLEEP_START, AnimationClipId.SLEEP_LOOP}:
            return AnimationState.SLEEPING
        return AnimationState.WAKING


if __name__ == "__main__":
    unittest.main()
