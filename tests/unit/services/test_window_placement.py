"""Tests for framework-free window placement helpers."""

from __future__ import annotations

import unittest

from project_akiha.services.window_placement import (
    ScreenBounds,
    WindowSize,
    clamp_window_position,
)
from project_akiha.services.window_state import WindowPosition


class WindowPlacementTest(unittest.TestCase):
    """Verify restored window positions stay visible."""

    def test_keeps_visible_position_unchanged(self) -> None:
        position = clamp_window_position(
            position=WindowPosition(x=100, y=120),
            window_size=WindowSize(width=180, height=220),
            screen_bounds=ScreenBounds(x=0, y=0, width=1920, height=1080),
        )

        self.assertEqual(position, WindowPosition(x=100, y=120))

    def test_clamps_position_beyond_right_and_bottom_edges(self) -> None:
        position = clamp_window_position(
            position=WindowPosition(x=1900, y=1000),
            window_size=WindowSize(width=180, height=220),
            screen_bounds=ScreenBounds(x=0, y=0, width=1920, height=1080),
        )

        self.assertEqual(position, WindowPosition(x=1740, y=860))

    def test_clamps_position_beyond_left_and_top_edges(self) -> None:
        position = clamp_window_position(
            position=WindowPosition(x=-400, y=-200),
            window_size=WindowSize(width=180, height=220),
            screen_bounds=ScreenBounds(x=0, y=0, width=1920, height=1080),
        )

        self.assertEqual(position, WindowPosition(x=0, y=0))

    def test_handles_screen_offset_from_secondary_monitor_layout(self) -> None:
        position = clamp_window_position(
            position=WindowPosition(x=-2200, y=100),
            window_size=WindowSize(width=180, height=220),
            screen_bounds=ScreenBounds(x=-1920, y=0, width=1920, height=1080),
        )

        self.assertEqual(position, WindowPosition(x=-1920, y=100))

    def test_handles_window_larger_than_screen(self) -> None:
        position = clamp_window_position(
            position=WindowPosition(x=500, y=500),
            window_size=WindowSize(width=4000, height=3000),
            screen_bounds=ScreenBounds(x=0, y=0, width=1920, height=1080),
        )

        self.assertEqual(position, WindowPosition(x=0, y=0))


if __name__ == "__main__":
    unittest.main()
