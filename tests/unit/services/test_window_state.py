"""Tests for window placement persistence."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.services.window_state import WindowPosition, WindowStateStore


class WindowStateStoreTest(unittest.TestCase):
    """Verify persisted window position behavior."""

    def test_missing_state_returns_none(self) -> None:
        with TemporaryDirectory() as directory:
            store = WindowStateStore(Path(directory) / "missing.json")

            self.assertIsNone(store.load_position())

    def test_round_trips_position(self) -> None:
        with TemporaryDirectory() as directory:
            store = WindowStateStore(Path(directory) / "pet_window.json")

            store.save_position(WindowPosition(x=321, y=654))

            self.assertEqual(store.load_position(), WindowPosition(x=321, y=654))

    def test_invalid_json_returns_none(self) -> None:
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "pet_window.json"
            state_path.write_text("{ nope", encoding="utf-8")
            store = WindowStateStore(state_path)

            self.assertIsNone(store.load_position())

    def test_rejects_non_integer_payload(self) -> None:
        with self.assertRaises(ValueError):
            WindowPosition.from_payload({"x": True, "y": 10})


if __name__ == "__main__":
    unittest.main()
