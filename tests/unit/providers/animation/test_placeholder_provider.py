"""Tests for the placeholder animation provider."""

from __future__ import annotations

import unittest

from project_akiha.core.state.animation import AnimationState
from project_akiha.providers.animation import PlaceholderAnimationProvider


class PlaceholderAnimationProviderTest(unittest.TestCase):
    """Verify placeholder animation frame generation."""

    def test_supports_all_current_animation_states(self) -> None:
        provider = PlaceholderAnimationProvider()

        self.assertEqual(provider.available_states(), frozenset(AnimationState))

    def test_idle_frame_bobs_for_first_half_of_period(self) -> None:
        provider = PlaceholderAnimationProvider()

        frame = provider.frame_for(AnimationState.IDLE, frame_number=0)

        self.assertEqual(frame.state, AnimationState.IDLE)
        self.assertEqual(frame.y_offset, 4)

    def test_idle_frame_returns_to_baseline_for_second_half_of_period(self) -> None:
        provider = PlaceholderAnimationProvider()

        frame = provider.frame_for(AnimationState.IDLE, frame_number=12)

        self.assertEqual(frame.y_offset, 0)

    def test_dragging_frame_does_not_bob(self) -> None:
        provider = PlaceholderAnimationProvider()

        frame = provider.frame_for(AnimationState.DRAGGING, frame_number=0)

        self.assertEqual(frame.y_offset, 0)

    def test_frame_index_wraps_to_cycle_length(self) -> None:
        provider = PlaceholderAnimationProvider()

        frame = provider.frame_for(AnimationState.IDLE, frame_number=241)

        self.assertEqual(frame.frame_index, 1)


if __name__ == "__main__":
    unittest.main()
