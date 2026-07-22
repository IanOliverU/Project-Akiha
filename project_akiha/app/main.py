"""Application entry point for Project Akiha."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from project_akiha.app.pet_controller import PetController
from project_akiha.config import AppConfig, load_config
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.animation import AnimationStateMachine
from project_akiha.providers.animation import (
    AnimationManifestError,
    AssetAnimationProvider,
    PlaceholderAnimationProvider,
)
from project_akiha.services.app_paths import get_app_paths
from project_akiha.services.config_store import UserConfigStore
from project_akiha.services.event_logger import EventLogger
from project_akiha.services.logging import configure_logging
from project_akiha.services.path_resolver import ConfigPathResolver
from project_akiha.services.window_placement import (
    ScreenBounds,
    WindowSize,
    clamp_window_position,
)
from project_akiha.services.window_state import WindowPosition, WindowStateStore
from project_akiha.ui.pet_renderer import PlaceholderPetRenderer, SpritePetRenderer
from project_akiha.ui.pet_window import PetWindow
from project_akiha.ui.settings_window import SettingsWindow
from project_akiha.ui.tray import AkihaTrayIcon


def main() -> int:
    """Build the application graph and start the Qt event loop."""
    app = QApplication(sys.argv)
    app.setApplicationName("Project Akiha")
    app.setQuitOnLastWindowClosed(False)

    paths = get_app_paths()
    path_resolver = ConfigPathResolver(
        project_root=paths.project_root,
        asset_dir=paths.asset_dir,
    )
    log_path = configure_logging(paths.log_dir)
    logger = logging.getLogger("project_akiha.app")
    logger.info("Starting Project Akiha. Log path: %s", log_path)

    user_config_store = UserConfigStore(paths.user_config_path)
    config = load_config(
        user_config_store.config_path
        if user_config_store.config_path.exists()
        else None
    )
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
    loaded_position = window_state_store.load_position() or fallback_position
    start_position = _clamp_to_primary_screen(
        app=app,
        position=loaded_position,
        window_size=WindowSize(
            width=config.pet_window.width,
            height=config.pet_window.height,
        ),
    )
    manifest_path = path_resolver.resolve_asset_path(
        config.pet_window.animation_manifest_path
    )
    animation_provider = _build_animation_provider(
        manifest_path,
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

    settings_window = SettingsWindow(
        config=config,
        log_dir=paths.log_dir,
    )

    def save_window_position(event: Event | None = None) -> None:
        del event
        window_state_store.save_position(WindowPosition(x=window.x(), y=window.y()))

    def apply_settings(updated_config: AppConfig) -> None:
        nonlocal config
        config = updated_config
        user_config_store.save_config(updated_config)
        window.apply_config(updated_config.pet_window)
        manifest = path_resolver.resolve_asset_path(
            updated_config.pet_window.animation_manifest_path
        )
        window.set_animation_provider(_build_animation_provider(manifest, logger))
        logger.info("Saved user config to %s", user_config_store.config_path)

    def reset_window_position() -> None:
        fallback = WindowPosition(
            x=config.pet_window.start_x,
            y=config.pet_window.start_y,
        )
        position = _clamp_to_primary_screen(
            app=app,
            position=fallback,
            window_size=WindowSize(
                width=config.pet_window.width,
                height=config.pet_window.height,
            ),
        )
        window.move(position.x, position.y)
        save_window_position()

    settings_window.settings_saved.connect(apply_settings)
    settings_window.position_reset_requested.connect(reset_window_position)

    def show_settings(event: Event | None = None) -> None:
        del event
        settings_window.show()
        settings_window.raise_()
        settings_window.activateWindow()

    event_bus.subscribe(EventType.SETTINGS_OPEN_REQUESTED, show_settings)
    event_bus.subscribe(EventType.PET_DRAG_ENDED, save_window_position)
    app.aboutToQuit.connect(save_window_position)

    tray_icon = AkihaTrayIcon(
        pet_window=window,
        settings_window=settings_window,
    )
    tray_icon.show()
    app._akiha_services = (
        event_logger,
        pet_controller,
        settings_window,
        tray_icon,
        user_config_store,
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


def _clamp_to_primary_screen(
    app: QApplication,
    position: WindowPosition,
    window_size: WindowSize,
) -> WindowPosition:
    screen = app.primaryScreen()
    if screen is None:
        return position

    geometry = screen.availableGeometry()
    return clamp_window_position(
        position=position,
        window_size=window_size,
        screen_bounds=ScreenBounds(
            x=geometry.x(),
            y=geometry.y(),
            width=geometry.width(),
            height=geometry.height(),
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
