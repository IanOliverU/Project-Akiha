"""Persistence for small window placement state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class WindowPosition:
    """A desktop window's top-left screen position."""

    x: int
    y: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> WindowPosition:
        """Create a position from validated JSON-like data."""
        x = payload.get("x")
        y = payload.get("y")
        if type(x) is not int or type(y) is not int:
            raise ValueError("Window position requires integer x and y values.")
        return cls(x=x, y=y)

    def to_payload(self) -> dict[str, int]:
        """Return a JSON-serializable representation."""
        return {"x": self.x, "y": self.y}


class WindowStateStore:
    """Read and write the persisted pet window position."""

    def __init__(self, state_path: Path) -> None:
        self._state_path = state_path

    def load_position(self) -> WindowPosition | None:
        """Return the last saved position, or None if unavailable."""
        if not self._state_path.exists():
            return None

        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return None
            return WindowPosition.from_payload(payload)
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def save_position(self, position: WindowPosition) -> None:
        """Persist the given position atomically enough for a tiny state file."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._state_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(position.to_payload(), indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self._state_path)
