"""Window placement helpers that do not depend on a UI framework."""

from __future__ import annotations

from dataclasses import dataclass

from project_akiha.services.window_state import WindowPosition


@dataclass(frozen=True, slots=True)
class WindowSize:
    """A desktop window's pixel dimensions."""

    width: int
    height: int


@dataclass(frozen=True, slots=True)
class ScreenBounds:
    """The usable rectangle for placing a desktop window."""

    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        """Return the right edge coordinate."""
        return self.x + self.width

    @property
    def bottom(self) -> int:
        """Return the bottom edge coordinate."""
        return self.y + self.height


def clamp_window_position(
    position: WindowPosition,
    window_size: WindowSize,
    screen_bounds: ScreenBounds,
) -> WindowPosition:
    """Keep a window's top-left position inside visible screen bounds."""
    max_x = max(screen_bounds.x, screen_bounds.right - window_size.width)
    max_y = max(screen_bounds.y, screen_bounds.bottom - window_size.height)

    return WindowPosition(
        x=_clamp(position.x, screen_bounds.x, max_x),
        y=_clamp(position.y, screen_bounds.y, max_y),
    )


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))
