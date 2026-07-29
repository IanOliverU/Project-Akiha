"""Tests for pet renderer helpers."""

from __future__ import annotations

import unittest

from PySide6.QtCore import QSize

from project_akiha.ui.pet_renderer import _scaled_viewport_size


class PetRendererTest(unittest.TestCase):
    """Verify image render tuning helpers."""

    def test_scaled_viewport_size_keeps_default_size(self) -> None:
        self.assertEqual(_scaled_viewport_size(QSize(180, 220), 100), QSize(180, 220))

    def test_scaled_viewport_size_applies_percent(self) -> None:
        self.assertEqual(_scaled_viewport_size(QSize(180, 220), 122), QSize(220, 268))

    def test_scaled_viewport_size_never_returns_zero(self) -> None:
        self.assertEqual(_scaled_viewport_size(QSize(1, 1), 1), QSize(1, 1))


if __name__ == "__main__":
    unittest.main()
