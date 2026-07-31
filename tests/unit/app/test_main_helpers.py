"""Tests for small application composition helpers."""

from __future__ import annotations

import unittest

from project_akiha.app.main import _collapse_nested_roots


class CollapseNestedRootsTest(unittest.TestCase):
    def test_removes_duplicate_and_nested_search_roots(self) -> None:
        roots = (
            r"C:\Users\Akiha\Desktop\Music",
            r"C:\Users\Akiha\Desktop",
            r"C:\Users\Akiha\Desktop",
            r"C:\Users\Akiha\Documents",
        )

        collapsed = _collapse_nested_roots(roots)

        self.assertEqual(
            collapsed,
            (
                r"C:\Users\Akiha\Desktop",
                r"C:\Users\Akiha\Documents",
            ),
        )

    def test_does_not_treat_similar_sibling_as_nested(self) -> None:
        roots = (
            r"C:\Users\Akiha\Music",
            r"C:\Users\Akiha\Music Archive",
        )

        self.assertEqual(_collapse_nested_roots(roots), roots)


if __name__ == "__main__":
    unittest.main()
