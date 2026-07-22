"""Application entry point for Project Akiha."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from project_akiha.app.pet_controller import PetController
from project_akiha.config import load_config
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.animation import AnimationStateMachine
from project_akiha.providers.animation import (
    AnimationManifestError,
    AssetAnimationProvider,
    PlaceholderAnimationProvider,
)
from project_akiha.services.app_paths import get_app_paths
from project_akiha.services.event_logger import EventLogger
from project_akiha.services.logging import configure_logging
from project_akiha.services.window_state import WindowPosition, WindowStateStore
from project_akiha.ui.pet_renderer import PlaceholderPetRenderer, SpritePetRenderer
from project_akiha.ui.pet_window import PetWindow
from project_akiha.ui.tray import AkihaTrayIcon


def main() -> int:
    """Build the application graph and start the Qt event loop."""
    app = QApplication(sys.argv)
    app.setApplicationName("Project Akiha")
    app.setQuitOnLastWindowClosed(False)

    paths = get_app_paths()
    log_path = configure_logging(paths.log_dir)
    logger = logging.getLogger("project_akiha.app")
    logger.info("Starting Project Akiha. Log path: %s", log_path)

    config = load_config()
    event_bus = EventBus()
    event_logger = EventLogger(event_bus)
    animation_state = AnimationStateMachine()
    pet_controller = PetController(
        event_bus=event_bus,
        animation_state=animation_state,
    )
    window_state_store = WindowStateStore(paths.state_dir / "pet_window.json")
    fallback_position = WindowPosition(
        x=config.pet_window.start_x,
        y=config.pet_window.start_y,
    )
    start_position = window_state_store.load_position() or fallback_position
    animation_provider = _build_animation_provider(
        Path(config.pet_window.animation_manifest_path),
        logger,
    )
    window = PetWindow(
        event_bus=event_bus,
        config=config.pet_window,
        animation_provider=animation_provider,
        renderer=SpritePetRenderer(fallback_renderer=PlaceholderPetRenderer()),
    )
    window.move(start_position.x, start_position.y)
    window.show()

    def save_window_position(event: Event | None = None) -> None:
        del event
        window_state_store.save_position(WindowPosition(x=window.x(), y=window.y()))

    event_bus.subscribe(EventType.PET_DRAG_ENDED, save_window_position)
    app.aboutToQuit.connect(save_window_position)

    tray_icon = AkihaTrayIcon(pet_window=window)
    tray_icon.show()
    app._akiha_services = (
        event_logger,
        pet_controller,
        tray_icon,
        window_state_store,
    )

    return app.exec()


def _build_animation_provider(
    manifest_path: Path,
    logger: logging.Logger,
) -> AssetAnimationProvider | PlaceholderAnimationProvider:
    if not manifest_path.exists():
        logger.info("Animation manifest not found; using placeholder animation.")
        return PlaceholderAnimationProvider()

    try:
        return AssetAnimationProvider.from_manifest(manifest_path)
    except AnimationManifestError as error:
        logger.warning("Animation manifest failed to load: %s", error)
        return PlaceholderAnimationProvider()


if __name__ == "__main__":
    raise SystemExit(main())
