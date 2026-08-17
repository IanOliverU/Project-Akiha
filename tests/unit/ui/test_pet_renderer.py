"""Tests for pet renderer helpers."""

from __future__ import annotations

import unittest

from PySide6.QtCore import QSize, Qt

from project_akiha.ui.pet_renderer import (
    _SPRITE_TRANSFORMATION_MODE,
    _scaled_viewport_size,
)


class PetRendererTest(unittest.TestCase):
    """Verify image render tuning helpers."""

    def test_scaled_viewport_size_keeps_default_size(self) -> None:
        self.assertEqual(_scaled_viewport_size(QSize(180, 220), 100), QSize(180, 220))

    def test_scaled_viewport_size_applies_percent(self) -> None:
        self.assertEqual(_scaled_viewport_size(QSize(180, 220), 122), QSize(220, 268))

    def test_scaled_viewport_size_never_returns_zero(self) -> None:
        self.assertEqual(_scaled_viewport_size(QSize(1, 1), 1), QSize(1, 1))

    def test_sprite_scaling_preserves_hard_pixel_edges(self) -> None:
        self.assertEqual(
            _SPRITE_TRANSFORMATION_MODE,
            Qt.TransformationMode.FastTransformation,
        )


if __name__ == "__main__":
    unittest.main()
