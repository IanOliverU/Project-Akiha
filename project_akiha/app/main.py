"""Application entry point for Project Akiha."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from project_akiha.app.chat_controller import ChatController
from project_akiha.app.pet_controller import PetController
from project_akiha.config import AIConfig, AppConfig, load_config
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.memory import StoredMessage
from project_akiha.core.state.animation import AnimationStateMachine
from project_akiha.database import SQLiteConversationRepository
from project_akiha.providers.ai import AIProvider, MockAIProvider, OllamaProvider
from project_akiha.providers.ai.base import ChatMessage
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
from project_akiha.ui.chat_window import ChatWindow
from project_akiha.ui.chat_worker import ChatResponseThread
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
    conversation_repository = SQLiteConversationRepository(paths.database_path)
    current_conversation = asyncio.run(
        conversation_repository.get_or_create_current_conversation()
    )
    recent_messages = asyncio.run(
        conversation_repository.get_recent_messages(current_conversation.id, limit=50)
    )
    chat_controller = ChatController(
        _build_ai_provider(config.ai, logger),
        system_prompt=config.personality.rendered_system_prompt(),
        conversation_repository=conversation_repository,
        conversation_id=current_conversation.id,
        initial_messages=_stored_messages_to_chat_messages(recent_messages),
    )
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
    chat_window = ChatWindow()
    _populate_chat_window(
        chat_window=chat_window,
        messages=chat_controller.messages,
        assistant_name=config.personality.character_name,
    )
    active_chat_threads: list[ChatResponseThread] = []

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
        chat_controller.set_ai_provider(_build_ai_provider(updated_config.ai, logger))
        chat_controller.set_system_prompt(
            updated_config.personality.rendered_system_prompt()
        )
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

    def show_chat(event: Event | None = None) -> None:
        del event
        chat_window.show()
        chat_window.raise_()
        chat_window.activateWindow()

    def submit_chat_message(message: str) -> None:
        chat_window.append_message("You", message)
        chat_window.set_busy(True)

        thread = ChatResponseThread(
            chat_controller=chat_controller,
            message=message,
        )
        active_chat_threads.append(thread)
        has_response_started = False

        def handle_delta(chunk: str) -> None:
            nonlocal has_response_started
            if not has_response_started:
                chat_window.begin_streaming_message(config.personality.character_name)
                has_response_started = True
            chat_window.append_stream_delta(chunk)

        def handle_error(error_message: str) -> None:
            logger.error("Chat message failed: %s", error_message)
            chat_window.append_error(error_message)

        def handle_cancelled() -> None:
            logger.info("Chat response cancelled by user.")
            chat_window.append_notice("Response stopped.")

        def cleanup_thread() -> None:
            chat_window.set_busy(False)
            if thread in active_chat_threads:
                active_chat_threads.remove(thread)
            thread.deleteLater()

        thread.response_delta.connect(handle_delta)
        thread.response_failed.connect(handle_error)
        thread.response_cancelled.connect(handle_cancelled)
        thread.finished.connect(cleanup_thread)
        thread.start()

    def cancel_active_chat() -> None:
        for thread in tuple(active_chat_threads):
            thread.cancel()

    chat_window.message_submitted.connect(submit_chat_message)
    chat_window.cancel_requested.connect(cancel_active_chat)
    event_bus.subscribe(EventType.CHAT_OPEN_REQUESTED, show_chat)
    event_bus.subscribe(EventType.SETTINGS_OPEN_REQUESTED, show_settings)
    event_bus.subscribe(EventType.PET_DRAG_ENDED, save_window_position)
    app.aboutToQuit.connect(save_window_position)

    tray_icon = AkihaTrayIcon(
        pet_window=window,
        chat_window=chat_window,
        settings_window=settings_window,
    )
    tray_icon.show()
    app._akiha_services = (
        chat_controller,
        active_chat_threads,
        chat_window,
        conversation_repository,
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


def _build_ai_provider(ai_config: AIConfig, logger: logging.Logger) -> AIProvider:
    if ai_config.provider == "ollama":
        logger.info(
            "Using Ollama AI provider with model %s at %s.",
            ai_config.ollama_model,
            ai_config.ollama_base_url,
        )
        return OllamaProvider(
            base_url=ai_config.ollama_base_url,
            model=ai_config.ollama_model,
            timeout_seconds=float(ai_config.request_timeout_seconds),
        )

    logger.info("Using mock AI provider.")
    return MockAIProvider()


def _stored_messages_to_chat_messages(
    messages: tuple[StoredMessage, ...],
) -> tuple[ChatMessage, ...]:
    return tuple(
        ChatMessage(role=message.role, content=message.content) for message in messages
    )


def _populate_chat_window(
    chat_window: ChatWindow,
    messages: tuple[ChatMessage, ...],
    assistant_name: str,
) -> None:
    for message in messages:
        if message.role == "user":
            chat_window.append_message("You", message.content)
        elif message.role == "assistant":
            chat_window.append_message(assistant_name, message.content)


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
