"""Application entry point for Project Akiha."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from project_akiha.app.activity_controller import ActivityController
from project_akiha.app.assistant_speech_controller import AssistantSpeechController
from project_akiha.app.assistant_translation_controller import (
    AssistantTranslationController,
)
from project_akiha.app.chat_controller import ChatController
from project_akiha.app.chat_voice_presenter import ChatVoicePresenter
from project_akiha.app.mood_animation_controller import MoodAnimationController
from project_akiha.app.mood_controller import MoodController
from project_akiha.app.pet_controller import PetController
from project_akiha.app.proactive_controller import ProactiveController
from project_akiha.app.proactive_delivery_controller import ProactiveDeliveryController
from project_akiha.app.proactive_speech_controller import ProactiveSpeechController
from project_akiha.app.scheduled_check_in_controller import ScheduledCheckInController
from project_akiha.app.shutdown import shutdown_runtime
from project_akiha.app.voice_capture_controller import VoiceCaptureController
from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_diagnostics_controller import VoiceDiagnosticsController
from project_akiha.app.voice_playback_controller import VoicePlaybackController
from project_akiha.app.voice_synthesis_controller import VoiceSynthesisController
from project_akiha.app.voice_transcription_controller import (
    VoiceTranscriptionController,
)
from project_akiha.config import AIConfig, AppConfig, VoiceConfig, load_config
from project_akiha.core.behavior import (
    CompanionMood,
    CompanionPresenceMapper,
    MoodAnimationMapper,
    MoodEngine,
    NotificationPolicy,
    ProactiveDeliveryService,
    ProactiveSuggestionEngine,
    ScheduledCheckInEngine,
)
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.memory import (
    ConversationSummarizer,
    HeuristicConversationSummarizer,
    MemoryPipeline,
    StoredMessage,
)
from project_akiha.core.memory.extraction import (
    HeuristicMemoryExtractor,
    MemoryExtractor,
)
from project_akiha.core.state.animation import AnimationStateMachine
from project_akiha.database import (
    SQLiteBehaviorRepository,
    SQLiteConversationRepository,
    SQLiteMemoryRepository,
)
from project_akiha.providers.ai import (
    AIProvider,
    MockAIProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    UnavailableAIProvider,
)
from project_akiha.providers.ai.base import ChatMessage
from project_akiha.providers.animation import (
    AnimationManifestError,
    AssetAnimationProvider,
    PlaceholderAnimationProvider,
)
from project_akiha.providers.voice import (
    FasterWhisperProvider,
    QtAudioPlayback,
    QtMicrophoneCapture,
    UnavailableVoiceOutputProvider,
    VoiceVoxProvider,
)
from project_akiha.services.app_paths import get_app_paths
from project_akiha.services.assistant_translation import AssistantTranslationService
from project_akiha.services.behavior_history import BehaviorHistoryRecorder
from project_akiha.services.config_store import UserConfigStore
from project_akiha.services.conversation_summary import AIConversationSummarizer
from project_akiha.services.credential_store import (
    CredentialStore,
    CredentialStoreError,
    EncryptedCredentialStore,
)
from project_akiha.services.diagnostics import (
    build_diagnostics_snapshot,
    render_diagnostics_summary,
)
from project_akiha.services.event_logger import EventLogger
from project_akiha.services.logging import configure_logging
from project_akiha.services.memory_extraction import AIMemoryExtractor
from project_akiha.services.path_resolver import ConfigPathResolver
from project_akiha.services.speech_identity import (
    AkihaSpeechStyleService,
    build_akiha_identity_system_prompt,
)
from project_akiha.services.speech_input import SpeechInputService
from project_akiha.services.speech_output import SpeechOutputService
from project_akiha.services.transcript_export import (
    render_chat_transcript,
    write_chat_transcript,
)
from project_akiha.services.voice_diagnostics import VoiceDiagnosticsService
from project_akiha.services.window_placement import (
    ScreenBounds,
    WindowSize,
    clamp_window_position,
)
from project_akiha.services.window_state import WindowPosition, WindowStateStore
from project_akiha.ui.behavior_history_window import BehaviorHistoryWindow
from project_akiha.ui.chat_window import ChatWindow
from project_akiha.ui.chat_worker import ChatResponseThread
from project_akiha.ui.memory_window import MemoryWindow
from project_akiha.ui.pet_renderer import PlaceholderPetRenderer, SpritePetRenderer
from project_akiha.ui.pet_window import PetWindow
from project_akiha.ui.proactive_delivery import QtProactiveDeliverySurface
from project_akiha.ui.settings_window import SettingsWindow
from project_akiha.ui.tray import AkihaTrayIcon

_AI_KEY_ENVIRONMENT_VARIABLES = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
    "grok": "XAI_API_KEY",
    "openai-compatible": "AKIHA_AI_API_KEY",
}


class _ChatErrorSurface(Protocol):
    def append_error(self, content: str) -> None:
        """Append a visible chat error."""


def main() -> int:
    """Run the application and log unrecoverable startup failures."""
    try:
        return _run_application()
    except Exception:
        _log_startup_failure()
        raise


def _run_application() -> int:
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
    logger.info(
        "Diagnostics snapshot:\n%s",
        render_diagnostics_summary(build_diagnostics_snapshot(paths)),
    )

    user_config_store = UserConfigStore(paths.user_config_path)
    config = load_config(
        user_config_store.config_path
        if user_config_store.config_path.exists()
        else None
    )
    credential_store = EncryptedCredentialStore(paths.credential_path)
    event_bus = EventBus()
    event_logger = EventLogger(event_bus)
    activity_controller = ActivityController(event_bus, config.behavior)
    voice_controller = VoiceController(event_bus, config.voice)
    mood_controller = MoodController(event_bus, MoodEngine())
    presence_mapper = CompanionPresenceMapper()
    notification_policy = NotificationPolicy(config.behavior)
    proactive_controller = ProactiveController(
        event_bus,
        ProactiveSuggestionEngine(notification_policy),
    )
    scheduled_check_in_engine = ScheduledCheckInEngine(
        notification_policy,
        config.behavior,
    )
    scheduled_check_in_controller = ScheduledCheckInController(
        event_bus,
        scheduled_check_in_engine,
    )
    behavior_repository = SQLiteBehaviorRepository(paths.database_path)
    behavior_history_recorder = BehaviorHistoryRecorder(
        event_bus=event_bus,
        repository=behavior_repository,
    )
    conversation_repository = SQLiteConversationRepository(paths.database_path)
    memory_repository = SQLiteMemoryRepository(paths.database_path)
    ai_provider = _build_ai_provider(config.ai, logger, credential_store)
    memory_pipeline = MemoryPipeline(
        memory_repository,
        extractor=_build_memory_extractor(ai_provider, config.ai),
    )
    current_conversation = asyncio.run(
        conversation_repository.get_or_create_current_conversation()
    )
    recent_messages = asyncio.run(
        conversation_repository.get_recent_messages(current_conversation.id, limit=50)
    )
    chat_controller = ChatController(
        ai_provider,
        system_prompt=build_akiha_identity_system_prompt(
            config.personality.rendered_system_prompt()
        ),
        conversation_repository=conversation_repository,
        conversation_id=current_conversation.id,
        initial_messages=_stored_messages_to_chat_messages(recent_messages),
        memory_pipeline=memory_pipeline,
        memory_repository=memory_repository,
        memory_enabled=config.memory.enabled,
        memory_retrieval_limit=config.memory.retrieval_limit,
        memory_requires_approval=config.memory.require_approval,
        conversation_summarizer=_build_conversation_summarizer(
            ai_provider,
            config.ai,
        ),
    )
    animation_state = AnimationStateMachine()
    pet_controller = PetController(
        event_bus=event_bus,
        animation_state=animation_state,
    )
    mood_animation_controller = MoodAnimationController(
        event_bus=event_bus,
        mapper=MoodAnimationMapper(),
        initial_animation_state=pet_controller.animation_state,
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
        data_dir=paths.data_dir,
        credential_store=credential_store,
    )
    chat_window = ChatWindow()
    assistant_translation_controller = AssistantTranslationController(
        service=AssistantTranslationService(ai_provider, conversation_repository),
        surface=chat_window,
        config=config.voice,
        message_id_provider=lambda: chat_controller.latest_assistant_message_id,
    )
    chat_voice_presenter = ChatVoicePresenter(
        event_bus=event_bus,
        surface=chat_window,
        config=config.voice,
        initial_state=voice_controller.state.value,
        initial_operation=voice_controller.operation,
    )
    microphone_capture = QtMicrophoneCapture(device_name=config.voice.input_device)
    speech_input_service = _build_speech_input_service(config.voice, paths.model_dir)
    voice_transcription_controller = VoiceTranscriptionController(
        event_bus=event_bus,
        voice_controller=voice_controller,
        service=speech_input_service,
    )
    audio_playback = QtAudioPlayback(
        device_name=config.voice.output_device,
        volume_percent=config.voice.volume_percent,
    )
    voice_playback_controller = VoicePlaybackController(
        event_bus=event_bus,
        voice_controller=voice_controller,
        playback=audio_playback,
    )
    speech_output_service = _build_speech_output_service(config.voice)
    voice_synthesis_controller = VoiceSynthesisController(
        event_bus=event_bus,
        voice_controller=voice_controller,
        service=speech_output_service,
        on_audio_synthesized=voice_playback_controller.play,
    )
    voice_capture_controller = VoiceCaptureController(
        event_bus=event_bus,
        voice_controller=voice_controller,
        capture=microphone_capture,
        config=config.voice,
        on_audio_captured=voice_transcription_controller.submit,
        on_audio_snapshot=voice_transcription_controller.submit_partial,
        on_microphone_test_captured=voice_transcription_controller.submit_test,
    )
    assistant_speech_controller = AssistantSpeechController(
        event_bus=event_bus,
        voice_controller=voice_controller,
        config=config.voice,
        style_service=AkihaSpeechStyleService(),
        mood_provider=lambda: mood_controller.snapshot.mood,
    )
    voice_diagnostics_controller = VoiceDiagnosticsController(
        event_bus=event_bus,
        voice_controller=voice_controller,
        service=VoiceDiagnosticsService(
            speech_input_service,
            speech_output_service,
        ),
        surface=settings_window,
    )
    memory_window = MemoryWindow()
    behavior_history_window = BehaviorHistoryWindow()
    _populate_chat_window(
        chat_window=chat_window,
        messages=recent_messages,
        assistant_name=config.personality.character_name,
        show_english_subtitles=config.voice.english_subtitles_enabled,
    )
    active_chat_threads: list[ChatResponseThread] = []

    def save_window_position(event: Event | None = None) -> None:
        del event
        window_state_store.save_position(WindowPosition(x=window.x(), y=window.y()))

    def apply_settings(updated_config: AppConfig) -> None:
        nonlocal config, speech_input_service, speech_output_service
        config = updated_config
        user_config_store.save_config(updated_config)
        window.apply_config(updated_config.pet_window)
        manifest = path_resolver.resolve_asset_path(
            updated_config.pet_window.animation_manifest_path
        )
        window.set_animation_provider(_build_animation_provider(manifest, logger))
        ai_provider = _build_ai_provider(
            updated_config.ai,
            logger,
            credential_store,
        )
        chat_controller.set_ai_provider(ai_provider)
        assistant_translation_controller.apply_service(
            AssistantTranslationService(ai_provider, conversation_repository)
        )
        assistant_translation_controller.apply_config(updated_config.voice)
        chat_controller.set_conversation_summarizer(
            _build_conversation_summarizer(ai_provider, updated_config.ai)
        )
        memory_pipeline.set_extractor(
            _build_memory_extractor(ai_provider, updated_config.ai)
        )
        chat_controller.set_system_prompt(
            build_akiha_identity_system_prompt(
                updated_config.personality.rendered_system_prompt()
            )
        )
        chat_controller.set_memory_enabled(updated_config.memory.enabled)
        chat_controller.set_memory_retrieval_limit(
            updated_config.memory.retrieval_limit
        )
        chat_controller.set_memory_requires_approval(
            updated_config.memory.require_approval
        )
        activity_controller.apply_config(updated_config.behavior)
        chat_voice_presenter.apply_config(updated_config.voice)
        voice_controller.apply_config(updated_config.voice)
        assistant_speech_controller.apply_config(updated_config.voice)
        speech_input_service = _build_speech_input_service(
            updated_config.voice,
            paths.model_dir,
        )
        speech_output_service = _build_speech_output_service(updated_config.voice)
        voice_transcription_controller.apply_service(speech_input_service)
        voice_synthesis_controller.apply_service(speech_output_service)
        voice_diagnostics_controller.apply_service(
            VoiceDiagnosticsService(
                speech_input_service,
                speech_output_service,
            )
        )
        voice_playback_controller.apply_config(updated_config.voice)
        voice_capture_controller.apply_config(updated_config.voice)
        notification_policy.update_config(updated_config.behavior)
        scheduled_check_in_engine.update_config(updated_config.behavior)
        proactive_controller.evaluate_snapshot(activity_controller.snapshot)
        scheduled_check_in_controller.tick(activity_controller.snapshot)
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
    settings_window.voice_health_check_requested.connect(
        voice_diagnostics_controller.check_health
    )
    settings_window.voice_microphone_test_requested.connect(
        voice_diagnostics_controller.toggle_microphone_test
    )
    settings_window.voice_output_test_requested.connect(
        voice_diagnostics_controller.toggle_output_test
    )

    def show_settings(event: Event | None = None) -> None:
        del event
        settings_window.show()
        settings_window.raise_()
        settings_window.activateWindow()

    def refresh_memory_window() -> None:
        memories = asyncio.run(memory_repository.get_recent_memories(limit=100))
        archived_memories = asyncio.run(
            memory_repository.get_archived_memories(limit=100)
        )
        memory_window.update_memories(memories)
        memory_window.update_archived_memories(archived_memories)
        memory_window.update_pending_memories(chat_controller.pending_memories)

    def show_memory_manager() -> None:
        refresh_memory_window()
        memory_window.show()
        memory_window.raise_()
        memory_window.activateWindow()

    def delete_memory(memory_id: int) -> None:
        asyncio.run(memory_repository.delete_memory(memory_id))
        refresh_memory_window()
        memory_window.append_notice("Memory deleted.")

    def edit_memory(
        memory_id: int,
        content: str,
        importance: int,
        tags: tuple[str, ...],
    ) -> None:
        try:
            asyncio.run(
                memory_repository.update_memory(
                    memory_id=memory_id,
                    content=content,
                    importance=importance,
                    tags=tags,
                )
            )
        except ValueError as error:
            memory_window.append_notice(str(error))
            return

        refresh_memory_window()
        memory_window.append_notice("Memory updated.")

    def archive_memory(memory_id: int) -> None:
        asyncio.run(memory_repository.archive_memory(memory_id))
        refresh_memory_window()
        memory_window.append_notice("Memory archived.")

    def restore_memory(memory_id: int) -> None:
        asyncio.run(memory_repository.restore_memory(memory_id))
        refresh_memory_window()
        memory_window.append_notice("Memory restored.")

    def clear_memories() -> None:
        asyncio.run(memory_repository.clear_memories())
        refresh_memory_window()
        memory_window.append_notice("All memories cleared.")

    def reflect_on_memories() -> None:
        queued_count = asyncio.run(chat_controller.reflect_on_memories())
        refresh_memory_window()
        if queued_count == 0:
            memory_window.append_notice("No reflection memories found.")
            return

        noun = "memory" if queued_count == 1 else "memories"
        memory_window.append_notice(f"{queued_count} reflection {noun} queued.")

    def approve_pending_memory(pending_memory_id: int) -> None:
        asyncio.run(chat_controller.approve_pending_memory(pending_memory_id))
        refresh_memory_window()
        memory_window.append_notice("Pending memory approved.")

    def reject_pending_memory(pending_memory_id: int) -> None:
        chat_controller.reject_pending_memory(pending_memory_id)
        refresh_memory_window()
        memory_window.append_notice("Pending memory rejected.")

    def clear_pending_memories() -> None:
        chat_controller.clear_pending_memories()
        refresh_memory_window()
        memory_window.append_notice("Pending memories cleared.")

    def refresh_behavior_history_window() -> None:
        events = asyncio.run(behavior_repository.get_recent_events(limit=200))
        behavior_history_window.update_events(events)

    def show_behavior_history() -> None:
        refresh_behavior_history_window()
        behavior_history_window.show()
        behavior_history_window.raise_()
        behavior_history_window.activateWindow()

    def clear_behavior_history() -> None:
        asyncio.run(behavior_repository.clear_events())
        refresh_behavior_history_window()
        behavior_history_window.append_notice("Behavior history cleared.")

    def clear_matching_behavior_history(event_type: str, kind: str) -> None:
        deleted_count = asyncio.run(
            behavior_repository.clear_events_matching(
                event_type=event_type or None,
                kind=kind or None,
            )
        )
        refresh_behavior_history_window()
        noun = "event" if deleted_count == 1 else "events"
        behavior_history_window.append_notice(
            f"{deleted_count} matching behavior {noun} cleared."
        )

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
            _handle_chat_failure(error_message, chat_window, logger)

        def handle_cancelled() -> None:
            logger.info("Chat response cancelled by user.")
            chat_window.append_notice("Response stopped.")

        def cleanup_thread() -> None:
            chat_window.set_busy(False)
            if thread in active_chat_threads:
                active_chat_threads.remove(thread)
            thread.deleteLater()

        thread.response_delta.connect(handle_delta)
        thread.response_ready.connect(
            assistant_speech_controller.submit_assistant_reply
        )
        thread.response_ready.connect(
            assistant_translation_controller.translate_assistant_response
        )
        thread.response_failed.connect(handle_error)
        thread.response_cancelled.connect(handle_cancelled)
        thread.finished.connect(cleanup_thread)
        thread.start()

    def cancel_active_chat() -> None:
        for thread in tuple(active_chat_threads):
            thread.cancel()

    def start_new_chat() -> None:
        if active_chat_threads:
            chat_window.append_notice(
                "Stop the current response before starting a new chat."
            )
            return

        asyncio.run(chat_controller.start_new_conversation())
        assistant_translation_controller.cancel(wait_ms=0)
        event_bus.publish(EventType.VOICE_SPEAK_STOP_REQUESTED)
        voice_synthesis_controller.clear_replay()
        chat_window.clear_history()
        chat_window.append_notice("New chat started.")
        chat_window.set_status("Ready")
        logger.info("Started a new chat conversation.")

    def clear_current_chat() -> None:
        if active_chat_threads:
            chat_window.append_notice("Stop the current response before clearing chat.")
            return

        asyncio.run(chat_controller.clear_current_conversation())
        assistant_translation_controller.cancel(wait_ms=0)
        event_bus.publish(EventType.VOICE_SPEAK_STOP_REQUESTED)
        voice_synthesis_controller.clear_replay()
        chat_window.clear_history()
        chat_window.append_notice("Chat cleared.")
        chat_window.set_status("Ready")
        logger.info("Cleared current chat conversation.")

    def export_current_chat(selected_path: str) -> None:
        if active_chat_threads:
            chat_window.append_notice(
                "Stop the current response before exporting chat."
            )
            return

        messages = asyncio.run(chat_controller.get_export_messages())
        transcript = render_chat_transcript(
            messages,
            assistant_name=config.personality.character_name,
            include_english_subtitles=(config.voice.export_english_subtitles_enabled),
        )
        if not transcript:
            chat_window.append_notice("No chat messages to export.")
            return

        export_path = Path(selected_path)
        try:
            write_chat_transcript(export_path, transcript)
        except OSError as error:
            logger.error("Chat transcript export failed: %s", error)
            chat_window.append_error(f"Export failed: {error}")
            return

        chat_window.append_notice("Chat exported.")
        logger.info("Exported chat transcript to %s", export_path)

    chat_window.message_submitted.connect(submit_chat_message)
    chat_window.cancel_requested.connect(cancel_active_chat)
    chat_window.new_chat_requested.connect(start_new_chat)
    chat_window.clear_chat_requested.connect(clear_current_chat)
    chat_window.export_chat_requested.connect(export_current_chat)
    chat_window.voice_listen_requested.connect(
        lambda: event_bus.publish(EventType.VOICE_LISTEN_REQUESTED)
    )
    chat_window.voice_listen_stop_requested.connect(
        lambda: event_bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)
    )
    chat_window.voice_listen_cancel_requested.connect(
        lambda: event_bus.publish(EventType.VOICE_LISTEN_CANCEL_REQUESTED)
    )
    chat_window.voice_speak_stop_requested.connect(
        lambda: event_bus.publish(EventType.VOICE_SPEAK_STOP_REQUESTED)
    )
    chat_window.voice_replay_requested.connect(
        lambda: event_bus.publish(EventType.VOICE_REPLAY_REQUESTED)
    )
    memory_window.refresh_requested.connect(refresh_memory_window)
    memory_window.edit_requested.connect(edit_memory)
    memory_window.archive_requested.connect(archive_memory)
    memory_window.restore_requested.connect(restore_memory)
    memory_window.delete_requested.connect(delete_memory)
    memory_window.clear_requested.connect(clear_memories)
    memory_window.reflect_requested.connect(reflect_on_memories)
    memory_window.approve_requested.connect(approve_pending_memory)
    memory_window.reject_requested.connect(reject_pending_memory)
    memory_window.clear_pending_requested.connect(clear_pending_memories)
    behavior_history_window.refresh_requested.connect(refresh_behavior_history_window)
    behavior_history_window.clear_requested.connect(clear_behavior_history)
    behavior_history_window.clear_matching_requested.connect(
        clear_matching_behavior_history
    )
    event_bus.subscribe(EventType.CHAT_OPEN_REQUESTED, show_chat)
    event_bus.subscribe(EventType.SETTINGS_OPEN_REQUESTED, show_settings)
    event_bus.subscribe(
        EventType.BEHAVIOR_HISTORY_OPEN_REQUESTED, show_behavior_history
    )
    event_bus.subscribe(EventType.APP_QUIT_REQUESTED, lambda event: app.quit())
    settings_window.memory_manager_requested.connect(show_memory_manager)
    settings_window.behavior_history_requested.connect(show_behavior_history)
    event_bus.subscribe(EventType.PET_DRAG_ENDED, save_window_position)

    def tick_behavior() -> None:
        activity = activity_controller.tick()
        scheduled_check_in_controller.tick(activity)

    activity_tick_timer = QTimer()
    activity_tick_timer.timeout.connect(tick_behavior)
    activity_tick_timer.start(30_000)

    def shutdown_app() -> None:
        ai_discovery_stopped = settings_window.cancel_ai_discovery()
        if not ai_discovery_stopped:
            logger.warning("AI provider discovery did not stop before shutdown.")
        translations_stopped = assistant_translation_controller.cancel()
        if not translations_stopped:
            logger.warning("Assistant translation did not stop before shutdown.")
        result = shutdown_runtime(
            activity_timer=activity_tick_timer,
            active_chat_threads=active_chat_threads,
            save_window_position=save_window_position,
            logger=logger,
            voice_capture=voice_capture_controller,
            voice_diagnostics=voice_diagnostics_controller,
            voice_transcription=voice_transcription_controller,
            voice_synthesis=voice_synthesis_controller,
            voice_playback=voice_playback_controller,
        )
        logger.info(
            "Shutdown cleanup complete: position_saved=%s, timer_stopped=%s, "
            "cancelled_threads=%s, unfinished_threads=%s, "
            "voice_capture_stopped=%s, voice_diagnostics_stopped=%s, "
            "voice_transcription_stopped=%s, "
            "voice_synthesis_stopped=%s, voice_playback_stopped=%s, "
            "ai_discovery_stopped=%s, translations_stopped=%s.",
            result.position_saved,
            result.timer_stopped,
            result.cancelled_threads,
            result.unfinished_threads,
            result.voice_capture_stopped,
            result.voice_diagnostics_stopped,
            result.voice_transcription_stopped,
            result.voice_synthesis_stopped,
            result.voice_playback_stopped,
            ai_discovery_stopped,
            translations_stopped,
        )

    app.aboutToQuit.connect(shutdown_app)

    tray_icon = AkihaTrayIcon(
        pet_window=window,
        chat_window=chat_window,
        settings_window=settings_window,
        quit_callback=app.quit,
    )

    def apply_presence(event: Event) -> None:
        mood_value = event.payload.get("mood")
        if not isinstance(mood_value, str):
            return

        try:
            mood = CompanionMood(mood_value)
        except ValueError:
            return

        presence_text = presence_mapper.text_for(mood)
        chat_window.set_presence_text(presence_text)
        tray_icon.set_presence_text(presence_text)

    event_bus.subscribe(EventType.MOOD_STATE_CHANGED, apply_presence)
    chat_window.set_presence_text(
        presence_mapper.text_for(mood_controller.snapshot.mood)
    )
    tray_icon.set_presence_text(presence_mapper.text_for(mood_controller.snapshot.mood))
    tray_icon.behavior_history_requested.connect(show_behavior_history)
    tray_icon.show()
    proactive_delivery_controller = ProactiveDeliveryController(
        event_bus=event_bus,
        delivery_service=ProactiveDeliveryService(),
        surface=QtProactiveDeliverySurface(
            chat_window=chat_window,
            tray_icon=tray_icon,
        ),
    )
    proactive_speech_controller = ProactiveSpeechController(
        event_bus=event_bus,
        speech_controller=assistant_speech_controller,
    )
    app._akiha_services = (
        assistant_speech_controller,
        assistant_translation_controller,
        chat_controller,
        activity_controller,
        activity_tick_timer,
        active_chat_threads,
        behavior_history_window,
        behavior_history_recorder,
        behavior_repository,
        chat_voice_presenter,
        chat_window,
        conversation_repository,
        event_logger,
        memory_pipeline,
        memory_repository,
        memory_window,
        mood_animation_controller,
        mood_controller,
        notification_policy,
        pet_controller,
        presence_mapper,
        proactive_controller,
        proactive_delivery_controller,
        proactive_speech_controller,
        scheduled_check_in_controller,
        scheduled_check_in_engine,
        settings_window,
        tray_icon,
        user_config_store,
        voice_capture_controller,
        voice_controller,
        voice_diagnostics_controller,
        voice_playback_controller,
        voice_synthesis_controller,
        voice_transcription_controller,
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


def _handle_chat_failure(
    error_message: str,
    chat_window: _ChatErrorSurface,
    logger: logging.Logger,
) -> None:
    """Log a provider failure and surface it in the chat window."""
    message = error_message.strip() or "Unknown chat provider failure."
    logger.error("AI provider response failed: %s", message)
    chat_window.append_error(message)


def _log_startup_failure() -> None:
    """Best-effort logging for unrecoverable startup failures."""
    try:
        paths = get_app_paths()
        configure_logging(paths.log_dir)
        logging.getLogger("project_akiha.app").exception(
            "Project Akiha failed during startup."
        )
    except Exception:
        logging.getLogger("project_akiha.app").exception(
            "Project Akiha failed during startup, and startup logging failed."
        )


def _build_ai_provider(
    ai_config: AIConfig,
    logger: logging.Logger,
    credential_store: CredentialStore,
) -> AIProvider:
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

    if ai_config.uses_hosted_api:
        api_key = _resolve_ai_api_key(ai_config.provider, credential_store, logger)
        if ai_config.requires_api_key and not api_key:
            logger.warning(
                "Hosted AI provider %s has no configured API key.",
                ai_config.provider,
            )
            return UnavailableAIProvider(
                f"No API key is configured for {ai_config.provider}. "
                "Open Settings > AI and save an API key."
            )
        logger.info(
            "Using hosted AI provider %s with model %s at %s.",
            ai_config.provider,
            ai_config.hosted_model,
            ai_config.hosted_base_url,
        )
        return OpenAICompatibleProvider(
            base_url=ai_config.hosted_base_url,
            model=ai_config.hosted_model,
            api_key=api_key or "",
            timeout_seconds=float(ai_config.request_timeout_seconds),
            provider_name=ai_config.provider,
        )

    logger.info("Using mock AI provider.")
    return MockAIProvider()


def _resolve_ai_api_key(
    provider: str,
    credential_store: CredentialStore,
    logger: logging.Logger,
) -> str | None:
    try:
        saved_key = credential_store.get_secret(provider)
    except CredentialStoreError:
        logger.exception("Could not read the encrypted %s API key.", provider)
        saved_key = None
    if saved_key:
        return saved_key
    environment_name = _AI_KEY_ENVIRONMENT_VARIABLES.get(provider)
    if environment_name is None:
        return None
    environment_value = os.environ.get(environment_name, "").strip()
    return environment_value or None


def _build_speech_input_service(
    voice_config: VoiceConfig,
    model_dir: Path,
) -> SpeechInputService:
    return SpeechInputService(
        FasterWhisperProvider(
            model_size=voice_config.input_model,
            language=voice_config.input_language,
            download_root=model_dir / "faster-whisper",
        )
    )


def _build_speech_output_service(voice_config: VoiceConfig) -> SpeechOutputService:
    if voice_config.output_provider == "disabled":
        return SpeechOutputService(
            UnavailableVoiceOutputProvider("Speech output is disabled.")
        )
    return SpeechOutputService(
        VoiceVoxProvider(
            base_url=voice_config.output_base_url,
            timeout_seconds=float(voice_config.request_timeout_seconds),
        )
    )


def _build_conversation_summarizer(
    ai_provider: AIProvider,
    ai_config: AIConfig,
) -> ConversationSummarizer:
    if ai_config.provider != "mock":
        return AIConversationSummarizer(ai_provider)

    return HeuristicConversationSummarizer()


def _build_memory_extractor(
    ai_provider: AIProvider,
    ai_config: AIConfig,
) -> MemoryExtractor:
    if ai_config.provider != "mock":
        return AIMemoryExtractor(ai_provider)

    return HeuristicMemoryExtractor()


def _stored_messages_to_chat_messages(
    messages: tuple[StoredMessage, ...],
) -> tuple[ChatMessage, ...]:
    return tuple(
        ChatMessage(role=message.role, content=message.content) for message in messages
    )


def _populate_chat_window(
    chat_window: ChatWindow,
    messages: tuple[ChatMessage | StoredMessage, ...],
    assistant_name: str,
    *,
    show_english_subtitles: bool = False,
) -> None:
    for message in messages:
        if message.role == "user":
            chat_window.append_message("You", message.content)
        elif message.role == "assistant":
            chat_window.append_message(assistant_name, message.content)
            translation = getattr(message, "english_translation", None)
            if (
                show_english_subtitles
                and isinstance(translation, str)
                and translation.strip()
            ):
                chat_window.append_assistant_translation(translation)


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


def _write_startup_crash_log() -> None:
    """Best-effort traceback capture for GUI-subsystem startup failures."""
    try:
        log_dir = get_app_paths().log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "startup-crash.log").write_text(
            traceback.format_exc(),
            encoding="utf-8",
        )
    except Exception:
        return


if __name__ == "__main__":
    try:
        exit_code = main()
    except BaseException:
        _write_startup_crash_log()
        raise
    raise SystemExit(exit_code)
