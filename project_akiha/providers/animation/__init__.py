"""Animation provider interfaces and implementations."""

from project_akiha.providers.animation.base import AnimationFrame, AnimationProvider
from project_akiha.providers.animation.placeholder_provider import (
    PlaceholderAnimationProvider,
)

__all__ = [
    "AnimationFrame",
    "AnimationProvider",
    "PlaceholderAnimationProvider",
]
