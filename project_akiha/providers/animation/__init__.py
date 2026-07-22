"""Animation provider interfaces and implementations."""

from project_akiha.providers.animation.asset_provider import (
    AnimationClip,
    AnimationManifestError,
    AssetAnimationProvider,
)
from project_akiha.providers.animation.base import AnimationFrame, AnimationProvider
from project_akiha.providers.animation.placeholder_provider import (
    PlaceholderAnimationProvider,
)

__all__ = [
    "AnimationClip",
    "AnimationFrame",
    "AnimationManifestError",
    "AnimationProvider",
    "AssetAnimationProvider",
    "PlaceholderAnimationProvider",
]
