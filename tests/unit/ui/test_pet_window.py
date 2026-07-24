"""Tests for the desktop pet window animation behavior."""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from project_akiha.config import PetWindowConfig
from project_akiha.core.events.bus import EventBus
from project_akiha.core.state.animation import AnimationState
from project_akiha.providers.animation.base import AnimationFrame
from project_akiha.ui.pet_window import PetWindow


class PetWindowTest(unittest.TestCase):
    """Verify pet window frame presentation behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def tearDown(self) -> None:
        if hasattr(self, "_window"):
            self._window.close()

    def test_walking_left_mirrors_animation_frame(self) -> None:
        self._window = self._make_window()
        self._window._current_state = AnimationState.WALKING
        self._window._walk_direction = -1

        frame = self._window._animation_frame_for_current_state()

        self.assertTrue(frame.mirrored_horizontally)

    def test_walking_right_keeps_animation_frame_orientation(self) -> None:
        self._window = self._make_window()
        self._window._current_state = AnimationState.WALKING
        self._window._walk_direction = 1

        frame = self._window._animation_frame_for_current_state()

        self.assertFalse(frame.mirrored_horizontally)

    def test_idle_does_not_mirror_when_last_walk_direction_was_left(self) -> None:
        self._window = self._make_window()
        self._window._current_state = AnimationState.IDLE
        self._window._walk_direction = -1

        frame = self._window._animation_frame_for_current_state()

        self.assertFalse(frame.mirrored_horizontally)

    def _make_window(self) -> PetWindow:
        window = PetWindow(
            event_bus=EventBus(),
            config=PetWindowConfig(always_on_top=False),
            animation_provider=_StaticAnimationProvider(),
            renderer=_NullRenderer(),
        )
        window._timer.stop()
        return window


class _StaticAnimationProvider:
    def available_states(self) -> frozenset[AnimationState]:
        return frozenset(AnimationState)

    def frame_for(
        self,
        state: AnimationState,
        frame_number: int,
    ) -> AnimationFrame:
        return AnimationFrame(state=state, frame_index=frame_number)


class _NullRenderer:
    def paint(self, painter, frame: AnimationFrame) -> None:  # noqa: ANN001
        del painter, frame


if __name__ == "__main__":
    unittest.main()
