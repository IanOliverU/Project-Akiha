"""Application entry point for Project Akiha."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from project_akiha.app.activity_controller import ActivityController
from project_akiha.app.assistant_speech_controller import AssistantSpeechController
from project_akiha.app.assistant_translation_controller import (
    AssistantTranslationController,
)
from project_akiha.app.chat_controller import ChatController
from project_akiha.app.chat_voice_presenter import ChatVoicePresenter
from project_akiha.app.local_conversation_session_controller import (
    LocalConversationSessionController,
)
from project_akiha.app.mood_animation_controller import MoodAnimationController
from project_akiha.app.mood_controller import MoodController
from project_akiha.app.pet_controller import PetController
from project_akiha.app.proactive_controller import ProactiveController
from project_akiha.app.proactive_delivery_controller import ProactiveDeliveryController
from project_akiha.app.proactive_speech_controller import ProactiveSpeechController
from project_akiha.app.push_to_talk_session_controller import (
    PushToTalkSessionController,
)
from project_akiha.app.response_completion_controller import (
    ResponseCompletionController,
)
from project_akiha.app.rolling_voice_transcription_controller import (
    RollingVoiceTranscriptionController,
)
from project_akiha.app.scheduled_check_in_controller import ScheduledCheckInController
from project_akiha.app.shutdown import shutdown_runtime
from project_akiha.app.streaming_voice_output_controller import (
    StreamingVoiceOutputController,
)
from project_akiha.app.talk_interruption_controller import (
    TalkInterruptionController,
)
from project_akiha.app.voice_capture_controller import VoiceCaptureController
from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_diagnostics_controller import VoiceDiagnosticsController
from project_akiha.app.voice_endpoint_controller import VoiceEndpointController
from project_akiha.app.voice_playback_controller import VoicePlaybackController
from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.app.voice_synthesis_controller import VoiceSynthesisController
from project_akiha.app.voice_transcription_controller import (
    VoiceTranscriptionController,
)
from project_akiha.config import AIConfig, AppConfig, VoiceConfig, load_config
from project_akiha.core.actions import (
    ActionPermissionPolicy,
    ActionRequest,
    ActionRequestValidator,
    AllowlistedApplicationExecutor,
    ApplicationCatalog,
    CloseAllowlistedApplicationExecutor,
    DirectorySearchExecutor,
    FileSearchExecutor,
    OpenDirectoryExecutor,
    OpenFileExecutor,
    ProtectedPathPolicy,
    build_default_action_registry,
)
from project_akiha.core.actions.registry import (
    APPLICATION_CLOSE_CAPABILITY,
    CLOSE_APPLICATION_ACTION,
    LAUNCH_APPLICATION_ACTION,
    OPEN_DIRECTORY_ACTION,
    OPEN_FILE_ACTION,
    SPOTIFY_OPEN_ALBUM_ACTION,
    SPOTIFY_OPEN_ARTIST_ACTION,
    SPOTIFY_PLAY_ALBUM_ACTION,
    SPOTIFY_PLAY_ARTIST_ACTION,
    SPOTIFY_PLAY_PLAYLIST_ACTION,
    SPOTIFY_PLAY_TRACK_ACTION,
    SPOTIFY_SEARCH_ALBUMS_ACTION,
    SPOTIFY_SEARCH_ARTISTS_ACTION,
    SPOTIFY_SEARCH_PLAYLISTS_ACTION,
    SPOTIFY_SEARCH_TRACKS_ACTION,
)
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
from project_akiha.core.voice_session import (
    ModularResponseContext,
    ModularResponseEvent,
    ModularResponseEventKind,
    ResponseSegment,
    VoiceProcessingMode,
)
from project_akiha.database import (
    SQLiteActionRepository,
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
from project_akiha.services.assistant_action_bridge import (
    AssistantActionBridge,
    AssistantActionDispatch,
)
from project_akiha.services.assistant_actions import AssistantActionService
from project_akiha.services.assistant_permissions import AssistantPermissionService
from project_akiha.services.assistant_tool_gateway import (
    AssistantToolKind,
    AssistantToolProposal,
    AssistantToolResultStore,
    LLMAssistantToolGateway,
    directory_name_matches,
    parse_directory_navigation_proposal,
    render_assistant_tool_clarification,
    should_request_tool_proposal,
)
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
from project_akiha.services.ephemeral_action_context import (
    EphemeralActionContext,
    EphemeralDirectoryReference,
    EphemeralReferenceError,
    EphemeralSelectionKind,
    EphemeralSelectionReference,
)
from project_akiha.services.event_logger import EventLogger
from project_akiha.services.intent_arbitration import (
    IntentArbiter,
    IntentProposal,
    IntentProposalSource,
)
from project_akiha.services.logging import configure_logging
from project_akiha.services.memory_extraction import AIMemoryExtractor
from project_akiha.services.path_resolver import ConfigPathResolver
from project_akiha.services.privacy_notice import (
    acknowledge_current_privacy_notice,
    privacy_notice_required,
)
from project_akiha.services.response_segment_renderer import (
    ResponseSegmentRenderer,
    SafeSpeechStyleRenderer,
)
from project_akiha.services.speech_identity import (
    AkihaSpeechStyleService,
    build_akiha_identity_system_prompt,
)
from project_akiha.services.speech_input import SpeechInputService
from project_akiha.services.speech_output import SpeechOutputService
from project_akiha.services.spotify_albums import (
    SpotifyAlbumSelectionStore,
    build_spotify_album_executors,
)
from project_akiha.services.spotify_client import SpotifyClient
from project_akiha.services.spotify_devices import (
    PermissionGatedSpotifyActivator,
    SpotifyDeviceCoordinator,
)
from project_akiha.services.spotify_favorites import build_spotify_favorites_executors
from project_akiha.services.spotify_playback import (
    SpotifyArtistSelectionStore,
    build_spotify_playback_executors,
)
from project_akiha.services.spotify_playlists import (
    SpotifyPlaylistSelectionStore,
    build_spotify_playlist_executors,
)
from project_akiha.services.spotify_preferences import SpotifyPreferenceRanker
from project_akiha.services.spotify_session import SpotifySession
from project_akiha.services.spotify_tracks import (
    SpotifyTrackSelectionStore,
    build_spotify_track_executors,
)
from project_akiha.services.transcript_export import (
    render_chat_transcript,
    write_chat_transcript,
)
from project_akiha.services.voice_diagnostics import VoiceDiagnosticsService
from project_akiha.services.voicevox_engine_manager import VoiceVoxEngineManager
from project_akiha.services.window_placement import (
    ScreenBounds,
    WindowSize,
    clamp_window_position,
)
from project_akiha.services.window_state import WindowPosition, WindowStateStore
from project_akiha.ui.assistant_action_history_window import (
    AssistantActionHistoryWindow,
)
from project_akiha.ui.assistant_action_worker import AssistantActionThread
from project_akiha.ui.assistant_tool_worker import (
    AssistantDirectorySearchThread,
    AssistantMediaSearchThread,
    AssistantToolProposalThread,
    DirectorySearchOutcome,
    MediaSearchOutcome,
)
from project_akiha.ui.behavior_history_window import BehaviorHistoryWindow
from project_akiha.ui.chat_window import ChatWindow
from project_akiha.ui.chat_worker import ChatResponseThread
from project_akiha.ui.memory_window import MemoryWindow
from project_akiha.ui.pet_renderer import PlaceholderPetRenderer, SpritePetRenderer
from project_akiha.ui.pet_window import PetWindow
from project_akiha.ui.privacy_notice import PrivacyNoticeDialog
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
    voice_session_coordinator = VoiceSessionCoordinator()

    def current_voice_processing_mode() -> VoiceProcessingMode:
        return (
            VoiceProcessingMode.HYBRID_API_MODULAR
            if config.ai.sends_text_off_device
            else VoiceProcessingMode.LOCAL_MODULAR
        )

    push_to_talk_session_controller = PushToTalkSessionController(
        event_bus=event_bus,
        voice_controller=voice_controller,
        session_coordinator=voice_session_coordinator,
        processing_mode_provider=current_voice_processing_mode,
        input_provider_name=lambda: config.voice.input_provider,
    )
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
    action_repository = SQLiteActionRepository(paths.database_path)
    action_path_policy = ProtectedPathPolicy.for_current_windows(
        credential_path=paths.credential_path,
    )
    application_catalog = ApplicationCatalog()
    spotify_session = SpotifySession(config.spotify, credential_store)
    spotify_client = SpotifyClient(config.spotify, spotify_session)
    spotify_preference_ranker = SpotifyPreferenceRanker(spotify_client)
    spotify_activator = PermissionGatedSpotifyActivator()
    spotify_device_coordinator = SpotifyDeviceCoordinator(
        spotify_client,
        spotify_activator,
        auto_launch_desktop_app=config.spotify.auto_launch_desktop_app,
    )
    assistant_action_service = AssistantActionService(
        ActionRequestValidator(build_default_action_registry(), action_path_policy),
        ActionPermissionPolicy(action_path_policy),
        action_repository,
        action_repository,
        executors=(
            FileSearchExecutor(),
            DirectorySearchExecutor(),
            OpenDirectoryExecutor(),
            OpenFileExecutor(),
            AllowlistedApplicationExecutor(application_catalog),
            CloseAllowlistedApplicationExecutor(application_catalog),
            *build_spotify_playback_executors(
                spotify_client,
                spotify_device_coordinator,
                spotify_preference_ranker,
            ),
            *build_spotify_track_executors(
                spotify_client,
                spotify_device_coordinator,
                spotify_preference_ranker,
            ),
            *build_spotify_album_executors(
                spotify_client,
                spotify_device_coordinator,
                spotify_preference_ranker,
            ),
            *build_spotify_playlist_executors(
                spotify_client,
                spotify_device_coordinator,
                spotify_preference_ranker,
            ),
            *build_spotify_favorites_executors(
                spotify_client,
                spotify_device_coordinator,
                spotify_preference_ranker,
            ),
        ),
    )
    spotify_activator.apply_service(assistant_action_service)
    assistant_permission_service = AssistantPermissionService(
        action_repository,
        action_path_policy,
    )
    assistant_action_bridge = AssistantActionBridge(assistant_action_service)
    behavior_history_recorder = BehaviorHistoryRecorder(
        event_bus=event_bus,
        repository=behavior_repository,
    )
    conversation_repository = SQLiteConversationRepository(paths.database_path)
    memory_repository = SQLiteMemoryRepository(paths.database_path)
    ai_provider = _build_ai_provider(config.ai, logger, credential_store)
    assistant_tool_gateway = LLMAssistantToolGateway(
        ai_provider,
        enabled=config.ai.assistant_tools_enabled,
    )
    assistant_tool_result_store = AssistantToolResultStore()
    spotify_artist_selection_store = SpotifyArtistSelectionStore()
    spotify_track_selection_store = SpotifyTrackSelectionStore()
    spotify_album_selection_store = SpotifyAlbumSelectionStore()
    spotify_playlist_selection_store = SpotifyPlaylistSelectionStore()
    ephemeral_action_context = EphemeralActionContext()
    intent_arbiter = IntentArbiter()
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
    privacy_notice = PrivacyNoticeDialog()

    def acknowledge_privacy_notice() -> None:
        nonlocal config
        config = config.with_privacy(acknowledge_current_privacy_notice(config.privacy))
        user_config_store.save_config(config)
        settings_window.update_config(config)
        logger.info(
            "Acknowledged privacy notice version %s.",
            config.privacy.notice_version_acknowledged,
        )

    privacy_notice.accepted.connect(acknowledge_privacy_notice)
    voicevox_engine_manager = VoiceVoxEngineManager(paths.project_root)

    def apply_voicevox_engine_config(voice_config: VoiceConfig) -> None:
        status = voicevox_engine_manager.apply_config(voice_config)
        settings_window.set_voice_engine_status(status.detail, status.is_error)
        logger.info("VOICEVOX Engine management state: %s.", status.state)
        if status.state == "starting":
            expected_url = voice_config.output_base_url

            def refresh_voicevox_engine_status() -> None:
                if config.voice.output_base_url != expected_url:
                    return
                refreshed = voicevox_engine_manager.refresh_status(expected_url)
                settings_window.set_voice_engine_status(
                    refreshed.detail,
                    refreshed.is_error,
                )
                logger.info(
                    "VOICEVOX Engine management state: %s.",
                    refreshed.state,
                )

            QTimer.singleShot(3_000, refresh_voicevox_engine_status)

    apply_voicevox_engine_config(config.voice)
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
    diagnostic_transcription_controller = VoiceTranscriptionController(
        event_bus=event_bus,
        voice_controller=voice_controller,
        service=speech_input_service,
    )
    voice_transcription_controller = RollingVoiceTranscriptionController(
        event_bus=event_bus,
        voice_controller=voice_controller,
        session_coordinator=voice_session_coordinator,
        service=speech_input_service,
        config=config.voice,
        diagnostic_controller=diagnostic_transcription_controller,
    )
    voice_endpoint_controller = VoiceEndpointController(
        event_bus=event_bus,
        voice_controller=voice_controller,
        config=config.voice,
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
    streaming_voice_output_controller = StreamingVoiceOutputController(
        event_bus=event_bus,
        voice_controller=voice_controller,
        playback_controller=voice_playback_controller,
        service=speech_output_service,
        on_response_spoken=voice_synthesis_controller.remember_spoken_text,
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
    response_segment_renderer = ResponseSegmentRenderer(
        SafeSpeechStyleRenderer(AkihaSpeechStyleService()),
        mood_provider=lambda: mood_controller.snapshot.mood,
    )
    response_completion_controller = ResponseCompletionController(
        assistant_speech_controller,
        assistant_translation_controller,
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
    assistant_action_history_window = AssistantActionHistoryWindow()
    _populate_chat_window(
        chat_window=chat_window,
        messages=recent_messages,
        assistant_name=config.personality.character_name,
        show_english_subtitles=config.voice.english_subtitles_enabled,
    )
    active_chat_threads: list[ChatResponseThread] = []
    interrupted_chat_threads: list[ChatResponseThread] = []
    active_action_threads: list[AssistantActionThread] = []
    active_tool_threads: list[
        AssistantToolProposalThread
        | AssistantMediaSearchThread
        | AssistantDirectorySearchThread
    ] = []

    def update_chat_busy_state() -> None:
        chat_window.set_busy(
            bool(active_chat_threads or active_action_threads or active_tool_threads)
        )

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
        assistant_tool_gateway.apply_provider(ai_provider)
        assistant_tool_gateway.set_enabled(updated_config.ai.assistant_tools_enabled)
        spotify_client.apply_config(updated_config.spotify)
        spotify_device_coordinator.apply_auto_launch(
            updated_config.spotify.auto_launch_desktop_app
        )
        assistant_tool_result_store.clear()
        ephemeral_action_context.clear()
        intent_arbiter.clear()
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
        apply_voicevox_engine_config(updated_config.voice)
        speech_input_service = _build_speech_input_service(
            updated_config.voice,
            paths.model_dir,
        )
        speech_output_service = _build_speech_output_service(updated_config.voice)
        voice_transcription_controller.apply_service(
            speech_input_service,
            updated_config.voice,
        )
        voice_synthesis_controller.apply_service(speech_output_service)
        streaming_voice_output_controller.apply_service(speech_output_service)
        voice_diagnostics_controller.apply_service(
            VoiceDiagnosticsService(
                speech_input_service,
                speech_output_service,
            )
        )
        voice_playback_controller.apply_config(updated_config.voice)
        voice_capture_controller.apply_config(updated_config.voice)
        voice_endpoint_controller.apply_config(updated_config.voice)
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
        refresh_assistant_permissions()
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

    def refresh_assistant_action_history_window() -> None:
        audits = asyncio.run(action_repository.get_recent_action_audits(limit=200))
        assistant_action_history_window.update_audits(audits)

    def clear_assistant_action_history() -> None:
        try:
            count = asyncio.run(action_repository.clear_action_audits())
            refresh_assistant_action_history_window()
            assistant_action_history_window.append_notice(
                f"Cleared {count} assistant action audit entries."
            )
        except OSError:
            logger.exception("Could not clear assistant action history.")
            assistant_action_history_window.append_notice(
                "Assistant action history could not be cleared."
            )

    def refresh_assistant_action_aliases() -> None:
        """Expose only approved directory basenames as voice-action aliases."""
        try:
            directories = asyncio.run(
                assistant_permission_service.get_approved_directories()
            )
            aliases = {
                Path(directory.root).name.casefold(): directory.root
                for directory in directories
                if Path(directory.root).name
            }
            assistant_action_bridge.set_directory_aliases(aliases)
        except Exception:
            logger.exception("Could not refresh assistant action aliases.")

    def refresh_assistant_permissions() -> None:
        try:
            directories = asyncio.run(
                assistant_permission_service.get_approved_directories()
            )
            refresh_assistant_action_aliases()
            applications = application_catalog.discover()
            grants = asyncio.run(assistant_permission_service.get_active_permissions())
            settings_window.update_assistant_permissions(
                directories,
                applications,
                grants,
            )
            settings_window.set_assistant_permission_status(
                "Permission controls are ready."
            )
        except Exception:
            logger.exception("Could not refresh assistant permissions.")
            settings_window.set_assistant_permission_status(
                "Permission controls could not be refreshed.",
                True,
            )

    def approve_assistant_directory(
        root: str,
        allow_search: bool,
        allow_open: bool,
    ) -> None:
        try:
            asyncio.run(
                assistant_permission_service.approve_directory(
                    root,
                    allow_search=allow_search,
                    allow_open=allow_open,
                )
            )
            refresh_assistant_permissions()
            settings_window.set_assistant_permission_status(
                "Directory permissions updated."
            )
        except (OSError, ValueError):
            logger.exception("Could not approve assistant directory.")
            settings_window.set_assistant_permission_status(
                "The directory could not be approved.",
                True,
            )

    def remove_assistant_directory(root: str) -> None:
        try:
            removed = asyncio.run(
                assistant_permission_service.remove_approved_directory(root)
            )
            refresh_assistant_permissions()
            settings_window.set_assistant_permission_status(
                (
                    "Directory permission removed."
                    if removed
                    else "No matching directory permission was found."
                ),
                not removed,
            )
        except (OSError, ValueError):
            logger.exception("Could not remove assistant directory permission.")
            settings_window.set_assistant_permission_status(
                "The directory permission could not be removed.",
                True,
            )

    def grant_assistant_application(application_id: str) -> None:
        try:
            asyncio.run(assistant_permission_service.grant_application(application_id))
            refresh_assistant_permissions()
            settings_window.set_assistant_permission_status(
                "Application permission enabled."
            )
        except (OSError, ValueError):
            logger.exception("Could not grant assistant application permission.")
            settings_window.set_assistant_permission_status(
                "The application permission could not be enabled.",
                True,
            )

    def revoke_assistant_application(application_id: str) -> None:
        try:
            removed = asyncio.run(
                assistant_permission_service.revoke_application(application_id)
            )
            refresh_assistant_permissions()
            settings_window.set_assistant_permission_status(
                (
                    "Application permission disabled."
                    if removed
                    else "No matching application permission was found."
                ),
                not removed,
            )
        except (OSError, ValueError):
            logger.exception("Could not revoke assistant application permission.")
            settings_window.set_assistant_permission_status(
                "The application permission could not be disabled.",
                True,
            )

    def grant_assistant_application_close(application_id: str) -> None:
        try:
            asyncio.run(
                assistant_permission_service.grant_application(
                    application_id,
                    APPLICATION_CLOSE_CAPABILITY,
                )
            )
            refresh_assistant_permissions()
            settings_window.set_assistant_permission_status(
                "Application close permission enabled."
            )
        except (OSError, ValueError):
            logger.exception("Could not grant application close permission.")
            settings_window.set_assistant_permission_status(
                "The application close permission could not be enabled.",
                True,
            )

    def revoke_assistant_application_close(application_id: str) -> None:
        try:
            removed = asyncio.run(
                assistant_permission_service.revoke_application(
                    application_id,
                    APPLICATION_CLOSE_CAPABILITY,
                )
            )
            refresh_assistant_permissions()
            settings_window.set_assistant_permission_status(
                (
                    "Application close permission disabled."
                    if removed
                    else "No matching application close permission was found."
                ),
                not removed,
            )
        except (OSError, ValueError):
            logger.exception("Could not revoke application close permission.")
            settings_window.set_assistant_permission_status(
                "The application close permission could not be disabled.",
                True,
            )

    def grant_spotify_playback() -> None:
        try:
            asyncio.run(assistant_permission_service.grant_spotify_playback())
            refresh_assistant_permissions()
            settings_window.set_assistant_permission_status(
                "Spotify playback permission enabled."
            )
        except OSError:
            logger.exception("Could not grant Spotify playback permission.")
            settings_window.set_assistant_permission_status(
                "Spotify playback permission could not be enabled.",
                True,
            )

    def revoke_spotify_playback() -> None:
        try:
            removed = asyncio.run(
                assistant_permission_service.revoke_spotify_playback()
            )
            refresh_assistant_permissions()
            settings_window.set_assistant_permission_status(
                (
                    "Spotify playback permission disabled."
                    if removed
                    else "No Spotify playback permission was found."
                ),
                not removed,
            )
        except OSError:
            logger.exception("Could not revoke Spotify playback permission.")
            settings_window.set_assistant_permission_status(
                "Spotify playback permission could not be disabled.",
                True,
            )

    def reset_assistant_permissions() -> None:
        try:
            count = asyncio.run(assistant_permission_service.reset_all_permissions())
            refresh_assistant_permissions()
            settings_window.set_assistant_permission_status(
                f"Reset {count} assistant permission(s)."
            )
        except OSError:
            logger.exception("Could not reset assistant permissions.")
            settings_window.set_assistant_permission_status(
                "Assistant permissions could not be reset.",
                True,
            )

    settings_window.assistant_permissions_refresh_requested.connect(
        refresh_assistant_permissions
    )
    settings_window.assistant_directory_approval_requested.connect(
        approve_assistant_directory
    )
    settings_window.assistant_directory_remove_requested.connect(
        remove_assistant_directory
    )
    settings_window.assistant_application_grant_requested.connect(
        grant_assistant_application
    )
    settings_window.assistant_application_revoke_requested.connect(
        revoke_assistant_application
    )
    settings_window.assistant_application_close_grant_requested.connect(
        grant_assistant_application_close
    )
    settings_window.assistant_application_close_revoke_requested.connect(
        revoke_assistant_application_close
    )
    settings_window.spotify_playback_grant_requested.connect(grant_spotify_playback)
    settings_window.spotify_playback_revoke_requested.connect(revoke_spotify_playback)
    settings_window.spotify_session_changed.connect(spotify_session.clear_access_token)
    settings_window.spotify_session_changed.connect(
        spotify_preference_ranker.invalidate
    )
    settings_window.assistant_permissions_reset_requested.connect(
        reset_assistant_permissions
    )

    def show_assistant_action_history() -> None:
        refresh_assistant_action_history_window()
        assistant_action_history_window.show()
        assistant_action_history_window.raise_()
        assistant_action_history_window.activateWindow()

    def start_action_thread(
        action_request: ActionRequest,
        *,
        confirmed: bool = False,
    ) -> None:
        chat_window.set_busy(True)
        action_thread = AssistantActionThread(
            assistant_action_bridge,
            action_request,
            confirmed=confirmed,
        )
        active_action_threads.append(action_thread)
        action_thread.result_ready.connect(handle_action_dispatch)
        action_thread.failed.connect(handle_action_failure)
        action_thread.cancelled.connect(
            lambda: chat_window.append_notice("Desktop action stopped.")
        )
        action_thread.finished.connect(
            lambda thread=action_thread: cleanup_action_thread(thread)
        )
        action_thread.start()

    def accept_intent(
        turn_id: str,
        action_category: str,
        source: IntentProposalSource,
    ) -> bool:
        proposal = IntentProposal(
            turn_id=turn_id,
            proposal_id=f"intent-proposal-{uuid4().hex}",
            action_category=action_category,
            source=source,
        )
        decision = (
            intent_arbiter.resolve_provider(proposal)
            if source is IntentProposalSource.PROVIDER
            else intent_arbiter.resolve_local(proposal)
        )
        logger.info(
            "Intent arbitration turn=%s category=%s source=%s decision=%s",
            decision.turn_id,
            decision.action_category,
            decision.source.name.casefold(),
            decision.reason.value,
        )
        if decision.accepted:
            return True
        chat_window.append_notice("A duplicate or conflicting action was ignored.")
        return False

    def start_intent_action(
        action_request: ActionRequest,
        *,
        turn_id: str,
        source: IntentProposalSource,
    ) -> None:
        if accept_intent(turn_id, action_request.action_id, source):
            start_action_thread(action_request)

    def handle_action_dispatch(dispatch: AssistantActionDispatch) -> None:
        result = dispatch.result
        matches = result.metadata.get("matches")
        if isinstance(matches, tuple):
            assistant_action_history_window.update_search_results(
                matches,
                summary=result.summary,
            )
        refresh_assistant_action_history_window()

        playlist_candidates = result.metadata.get("playlist_candidates")
        if dispatch.request.action_id in {
            SPOTIFY_PLAY_PLAYLIST_ACTION,
            SPOTIFY_SEARCH_PLAYLISTS_ACTION,
        } and isinstance(playlist_candidates, tuple):
            try:
                spotify_playlist_selection_store.replace(playlist_candidates)
                ephemeral_action_context.record_selection(
                    EphemeralSelectionKind.SPOTIFY_PLAYLIST,
                    len(playlist_candidates),
                    allowed_verbs=frozenset(("play",)),
                )
            except ValueError:
                chat_window.append_error(
                    "Akiha could not safely present those Spotify playlists."
                )
                return
            if not playlist_candidates:
                chat_window.append_message(
                    config.personality.character_name,
                    result.summary,
                )
                return
            lines = [
                f"{index}. {playlist.display_label}"
                + (
                    " (local favorite)"
                    if spotify_preference_ranker.is_preferred_cached(playlist)
                    else ""
                )
                for index, playlist in enumerate(playlist_candidates, start=1)
            ]
            chat_window.append_message(
                config.personality.character_name,
                (
                    "I found these Spotify playlists:\n"
                    if dispatch.request.action_id == SPOTIFY_SEARCH_PLAYLISTS_ACTION
                    else "I found several possible Spotify playlists:\n"
                )
                + "\n".join(lines)
                + '\nSay "Play playlist result 1" with the number you want.',
            )
            return

        album_candidates = result.metadata.get("album_candidates")
        if dispatch.request.action_id in {
            SPOTIFY_OPEN_ALBUM_ACTION,
            SPOTIFY_PLAY_ALBUM_ACTION,
            SPOTIFY_SEARCH_ALBUMS_ACTION,
        } and isinstance(album_candidates, tuple):
            if dispatch.request.action_id == SPOTIFY_SEARCH_ALBUMS_ACTION:
                allowed_album_actions = (
                    SPOTIFY_PLAY_ALBUM_ACTION,
                    SPOTIFY_OPEN_ALBUM_ACTION,
                )
            else:
                allowed_album_actions = (dispatch.request.action_id,)
            try:
                spotify_album_selection_store.replace(
                    album_candidates,
                    allowed_action_ids=allowed_album_actions,
                )
                ephemeral_action_context.record_selection(
                    EphemeralSelectionKind.SPOTIFY_ALBUM,
                    len(album_candidates),
                    allowed_verbs=frozenset(
                        "open" if action_id == SPOTIFY_OPEN_ALBUM_ACTION else "play"
                        for action_id in allowed_album_actions
                    ),
                )
            except ValueError:
                chat_window.append_error(
                    "Akiha could not safely present those Spotify albums."
                )
                return
            if not album_candidates:
                chat_window.append_message(
                    config.personality.character_name,
                    result.summary,
                )
                return
            lines = [
                f"{index}. {album.display_label}"
                + (
                    " (local favorite)"
                    if spotify_preference_ranker.is_preferred_cached(album)
                    else ""
                )
                for index, album in enumerate(album_candidates, start=1)
            ]
            if dispatch.request.action_id == SPOTIFY_SEARCH_ALBUMS_ACTION:
                follow_up = (
                    'Say "Play album result 1" or "Open album result 1" '
                    "with the number you want."
                )
            elif dispatch.request.action_id == SPOTIFY_OPEN_ALBUM_ACTION:
                follow_up = 'Say "Open album result 1" with the number you want.'
            else:
                follow_up = 'Say "Play album result 1" with the number you want.'
            chat_window.append_message(
                config.personality.character_name,
                (
                    "I found these Spotify albums:\n"
                    if dispatch.request.action_id == SPOTIFY_SEARCH_ALBUMS_ACTION
                    else "I found several possible Spotify albums:\n"
                )
                + "\n".join(lines)
                + "\n"
                + follow_up,
            )
            return

        track_candidates = result.metadata.get("track_candidates")
        if dispatch.request.action_id in {
            SPOTIFY_PLAY_TRACK_ACTION,
            SPOTIFY_SEARCH_TRACKS_ACTION,
        } and isinstance(track_candidates, tuple):
            try:
                spotify_track_selection_store.replace(track_candidates)
                ephemeral_action_context.record_selection(
                    EphemeralSelectionKind.SPOTIFY_TRACK,
                    len(track_candidates),
                    allowed_verbs=frozenset(("play",)),
                )
            except ValueError:
                chat_window.append_error(
                    "Akiha could not safely present those Spotify tracks."
                )
                return
            if not track_candidates:
                chat_window.append_message(
                    config.personality.character_name,
                    result.summary,
                )
                return
            lines = []
            for index, track in enumerate(track_candidates, start=1):
                label = track.display_label
                if track.album_name:
                    label = f"{label} [{track.album_name}]"
                if spotify_preference_ranker.is_preferred_cached(track):
                    label = f"{label} (local favorite)"
                lines.append(f"{index}. {label}")
            intro = (
                "I found these Spotify tracks:\n"
                if dispatch.request.action_id == SPOTIFY_SEARCH_TRACKS_ACTION
                else "I found several possible Spotify tracks:\n"
            )
            chat_window.append_message(
                config.personality.character_name,
                intro
                + "\n".join(lines)
                + '\nSay "Play track result 1" with the number you want.',
            )
            return

        artist_candidates = result.metadata.get("artist_candidates")
        if dispatch.request.action_id in {
            SPOTIFY_OPEN_ARTIST_ACTION,
            SPOTIFY_PLAY_ARTIST_ACTION,
            SPOTIFY_SEARCH_ARTISTS_ACTION,
        } and isinstance(artist_candidates, tuple):
            if dispatch.request.action_id == SPOTIFY_SEARCH_ARTISTS_ACTION:
                allowed_artist_actions = (
                    SPOTIFY_PLAY_ARTIST_ACTION,
                    SPOTIFY_OPEN_ARTIST_ACTION,
                )
            else:
                allowed_artist_actions = (dispatch.request.action_id,)
            try:
                spotify_artist_selection_store.replace(
                    artist_candidates,
                    allowed_action_ids=allowed_artist_actions,
                )
                ephemeral_action_context.record_selection(
                    EphemeralSelectionKind.SPOTIFY_ARTIST,
                    len(artist_candidates),
                    allowed_verbs=frozenset(
                        "open" if action_id == SPOTIFY_OPEN_ARTIST_ACTION else "play"
                        for action_id in allowed_artist_actions
                    ),
                )
            except ValueError:
                chat_window.append_error(
                    "Akiha could not safely present those Spotify artists."
                )
                return
            if not artist_candidates:
                chat_window.append_message(
                    config.personality.character_name,
                    result.summary,
                )
                return
            lines = [
                f"{index}. {artist.name}"
                + (
                    " (local favorite)"
                    if spotify_preference_ranker.is_preferred_cached(artist)
                    else ""
                )
                for index, artist in enumerate(artist_candidates, start=1)
            ]
            if dispatch.request.action_id == SPOTIFY_SEARCH_ARTISTS_ACTION:
                follow_up = (
                    'Say "Play artist result 1" or "Open artist result 1" '
                    "with the number you want."
                )
            elif dispatch.request.action_id == SPOTIFY_OPEN_ARTIST_ACTION:
                follow_up = 'Say "Open artist result 1" with the number you want.'
            else:
                follow_up = 'Say "Play artist result 1" with the number you want.'
            chat_window.append_message(
                config.personality.character_name,
                (
                    "I found these Spotify artists:\n"
                    if dispatch.request.action_id == SPOTIFY_SEARCH_ARTISTS_ACTION
                    else "I found several possible Spotify artists:\n"
                )
                + "\n".join(lines)
                + "\n"
                + follow_up,
            )
            return

        if result.status.value == "success":
            action_id = dispatch.request.action_id
            if action_id == LAUNCH_APPLICATION_ACTION:
                application_id = dispatch.request.parameters.get("application_id")
                if isinstance(application_id, str):
                    ephemeral_action_context.record_application(application_id)
            elif action_id == CLOSE_APPLICATION_ACTION:
                application_id = dispatch.request.parameters.get("application_id")
                ephemeral_action_context.clear_application(
                    application_id if isinstance(application_id, str) else None
                )
            if action_id.startswith("spotify.") and action_id not in {
                SPOTIFY_OPEN_ALBUM_ACTION,
                SPOTIFY_OPEN_ARTIST_ACTION,
                SPOTIFY_SEARCH_ALBUMS_ACTION,
                SPOTIFY_SEARCH_ARTISTS_ACTION,
                SPOTIFY_SEARCH_PLAYLISTS_ACTION,
                SPOTIFY_SEARCH_TRACKS_ACTION,
            }:
                ephemeral_action_context.record_spotify_activity()
            if dispatch.request.action_id in {
                SPOTIFY_OPEN_ARTIST_ACTION,
                SPOTIFY_PLAY_ARTIST_ACTION,
            }:
                spotify_artist_selection_store.clear()
                ephemeral_action_context.clear_selection()
            if dispatch.request.action_id == SPOTIFY_PLAY_TRACK_ACTION:
                spotify_track_selection_store.clear()
                ephemeral_action_context.clear_selection()
            if dispatch.request.action_id == SPOTIFY_PLAY_PLAYLIST_ACTION:
                playlist_name = result.metadata.get("playlist_name")
                playlist_uri = result.metadata.get("playlist_uri")
                playlist_owner = result.metadata.get("playlist_owner", "")
                if (
                    isinstance(playlist_name, str)
                    and isinstance(playlist_uri, str)
                    and isinstance(playlist_owner, str)
                ):
                    try:
                        spotify_playlist_selection_store.remember_selected(
                            playlist_name,
                            playlist_uri,
                            playlist_owner,
                        )
                    except ValueError:
                        logger.warning(
                            "Spotify returned invalid selected-playlist metadata."
                        )
                        spotify_playlist_selection_store.clear()
                    else:
                        spotify_playlist_selection_store.clear_candidates()
                        ephemeral_action_context.record_selected(
                            EphemeralSelectionKind.SPOTIFY_PLAYLIST,
                            allowed_verbs=frozenset(("play",)),
                        )
                else:
                    spotify_playlist_selection_store.clear()
                    ephemeral_action_context.clear_selection()
            if dispatch.request.action_id in {
                SPOTIFY_OPEN_ALBUM_ACTION,
                SPOTIFY_PLAY_ALBUM_ACTION,
            }:
                album_name = result.metadata.get("album_name")
                album_uri = result.metadata.get("album_uri")
                album_artist = result.metadata.get("album_artist", "")
                if (
                    isinstance(album_name, str)
                    and isinstance(album_uri, str)
                    and isinstance(album_artist, str)
                ):
                    try:
                        spotify_album_selection_store.remember_selected(
                            album_name,
                            album_uri,
                            album_artist,
                        )
                    except ValueError:
                        logger.warning(
                            "Spotify returned invalid selected-album metadata."
                        )
                        spotify_album_selection_store.clear()
                    else:
                        spotify_album_selection_store.clear_candidates()
                        ephemeral_action_context.record_selected(
                            EphemeralSelectionKind.SPOTIFY_ALBUM,
                            allowed_verbs=frozenset(("open", "play")),
                        )
                else:
                    spotify_album_selection_store.clear()
                    ephemeral_action_context.clear_selection()
            if dispatch.request.action_id == OPEN_DIRECTORY_ACTION:
                opened_directory = result.metadata.get("opened_directory")
                if isinstance(opened_directory, str):
                    ephemeral_action_context.record_directory(opened_directory)
                ephemeral_action_context.clear_selection()
            if dispatch.request.action_id == OPEN_FILE_ACTION:
                ephemeral_action_context.clear_selection()
            chat_window.append_message(
                config.personality.character_name, result.summary
            )
        elif result.status.value == "confirmation_required":
            if dispatch.request.action_id == "files.open":
                target = str(
                    dispatch.request.parameters.get("path", "the selected file")
                )
                answer = QMessageBox.question(
                    chat_window,
                    "Confirm file opening",
                    f"Open this passive file with its default application?\n\n{target}",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer == QMessageBox.StandardButton.Yes:
                    start_action_thread(dispatch.request, confirmed=True)
                else:
                    chat_window.append_notice("File opening was not confirmed.")
            else:
                chat_window.append_notice(
                    f"Action needs confirmation: {result.summary}"
                )
        else:
            chat_window.append_error(f"Action unavailable: {result.summary}")

    def handle_action_failure(error_message: str) -> None:
        logger.error("Direct assistant action failed: %s", error_message)
        chat_window.append_error("Akiha could not complete that desktop action.")

    def cleanup_action_thread(thread: AssistantActionThread) -> None:
        if thread in active_action_threads:
            active_action_threads.remove(thread)
        update_chat_busy_state()
        thread.deleteLater()
        event_bus.publish(
            EventType.VOICE_CONVERSATION_TURN_COMPLETED,
            {"source": "assistant_action"},
        )

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

    def start_chat_response(message: str) -> None:
        chat_window.set_busy(True)

        thread = ChatResponseThread(
            chat_controller=chat_controller,
            message=message,
            response_context=ModularResponseContext(
                response_id=uuid4().hex,
                processing_mode=(
                    VoiceProcessingMode.HYBRID_API_MODULAR
                    if config.ai.sends_text_off_device
                    else VoiceProcessingMode.LOCAL_MODULAR
                ),
            ),
            segment_renderer=response_segment_renderer,
        )
        active_chat_threads.append(thread)
        has_response_started = False
        has_streaming_speech = False

        def handle_speech_segment(segment: object) -> None:
            nonlocal has_streaming_speech
            if not isinstance(segment, ResponseSegment):
                return
            if streaming_voice_output_controller.submit(segment):
                has_streaming_speech = True

        def handle_response_event(event: object) -> None:
            nonlocal has_response_started
            if not isinstance(event, ModularResponseEvent):
                return
            if event.kind is ModularResponseEventKind.DELTA:
                if not has_response_started:
                    chat_window.begin_streaming_message(
                        config.personality.character_name
                    )
                    has_response_started = True
                chat_window.append_stream_delta(event.text or "")
            elif event.kind is ModularResponseEventKind.COMPLETED:
                response_completion_controller.complete(
                    event.text or "",
                    streaming_speech_started=has_streaming_speech,
                )
            elif event.kind is ModularResponseEventKind.FAILED:
                _handle_chat_failure(event.error_message or "", chat_window, logger)
            elif event.kind is ModularResponseEventKind.CANCELLED:
                if thread in interrupted_chat_threads:
                    logger.info("Chat response interrupted by a new Talk request.")
                    chat_window.append_notice("Response interrupted.")
                else:
                    logger.info("Chat response cancelled by user.")
                    chat_window.append_notice("Response stopped.")

        def cleanup_thread() -> None:
            if thread in active_chat_threads:
                active_chat_threads.remove(thread)
            if thread in interrupted_chat_threads:
                interrupted_chat_threads.remove(thread)
            update_chat_busy_state()
            thread.deleteLater()

        thread.speech_segment_ready.connect(handle_speech_segment)
        thread.modular_response_event.connect(handle_response_event)
        thread.finished.connect(cleanup_thread)
        thread.start()

    def searchable_assistant_roots() -> tuple[str, ...]:
        try:
            directories = asyncio.run(
                assistant_permission_service.get_approved_directories()
            )
        except Exception:
            logger.exception("Could not load searchable assistant roots.")
            return ()
        roots = tuple(
            directory.root
            for directory in directories
            if directory.can_search and directory.is_available
        )
        return _collapse_nested_roots(roots)

    def directory_navigation_roots(
        proposal: AssistantToolProposal,
    ) -> tuple[str, ...]:
        try:
            directories = asyncio.run(
                assistant_permission_service.get_approved_directories()
            )
        except Exception:
            logger.exception("Could not load directory navigation roots.")
            return ()
        eligible = tuple(
            directory
            for directory in directories
            if directory.can_search and directory.can_open and directory.is_available
        )
        navigation_context = ephemeral_action_context.current_directory
        if proposal.parent_name:
            roots = tuple(
                directory.root
                for directory in eligible
                if directory_name_matches(
                    proposal.parent_name,
                    Path(directory.root).name,
                )
            )
            if (
                navigation_context is not None
                and directory_name_matches(
                    proposal.parent_name,
                    Path(navigation_context).name,
                )
                and any(
                    action_path_policy.is_within(
                        navigation_context,
                        directory.root,
                    )
                    for directory in eligible
                )
            ):
                roots = (*roots, navigation_context)
            return _collapse_nested_roots(roots)
        if navigation_context is not None and any(
            action_path_policy.is_within(
                navigation_context,
                directory.root,
            )
            for directory in eligible
        ):
            return (navigation_context,)
        return _collapse_nested_roots(tuple(directory.root for directory in eligible))

    def start_directory_search(
        proposal: AssistantToolProposal,
        *,
        turn_id: str,
        source: IntentProposalSource,
    ) -> None:
        if not accept_intent(turn_id, "files.navigate_directory", source):
            update_chat_busy_state()
            return
        roots = directory_navigation_roots(proposal)
        if not roots:
            chat_window.append_error(
                "Action unavailable: The parent directory is not an approved "
                "search-and-open location."
            )
            update_chat_busy_state()
            return

        chat_window.set_busy(True)
        thread = AssistantDirectorySearchThread(
            assistant_action_bridge,
            proposal,
            roots,
        )
        active_tool_threads.append(thread)

        def handle_result(outcome: DirectorySearchOutcome) -> None:
            matches = outcome.matches[:10]
            assistant_tool_result_store.replace_directories(matches)
            ephemeral_action_context.record_selection(
                EphemeralSelectionKind.DIRECTORY,
                len(matches),
                allowed_verbs=frozenset(("open",)),
            )
            noun = "directory" if len(matches) == 1 else "directories"
            assistant_action_history_window.update_search_results(
                matches,
                summary=f"Found {len(matches)} matching {noun}.",
            )
            refresh_assistant_action_history_window()
            if not matches:
                chat_window.append_message(
                    config.personality.character_name,
                    "I could not find that directory beneath the approved " "location.",
                )
                return
            if len(matches) == 1:
                selected = matches[0]
                chat_window.append_message(
                    config.personality.character_name,
                    f"I found the {selected.name} directory.",
                )
                request = ActionRequest(
                    correlation_id=f"directory-open-{uuid4().hex}",
                    action_id=OPEN_DIRECTORY_ACTION,
                    source="directory_navigation",
                    parameters={"path": selected.path},
                )
                start_action_thread(request)
                return
            lines = [
                f"{index}. {match.name}" for index, match in enumerate(matches, start=1)
            ]
            chat_window.append_message(
                config.personality.character_name,
                "I found several matching directories:\n"
                + "\n".join(lines)
                + '\nSay "Open result 1" with the number you want.',
            )
            show_assistant_action_history()

        def handle_failure(error_message: str) -> None:
            logger.error("Directory navigation failed: %s", error_message)
            chat_window.append_error(
                "Akiha could not complete the approved directory search."
            )

        def handle_cancelled() -> None:
            chat_window.append_notice("Directory search stopped.")

        def cleanup_thread() -> None:
            if thread in active_tool_threads:
                active_tool_threads.remove(thread)
            update_chat_busy_state()
            thread.deleteLater()

        thread.result_ready.connect(handle_result)
        thread.failed.connect(handle_failure)
        thread.cancelled.connect(handle_cancelled)
        thread.finished.connect(cleanup_thread)
        thread.start()

    def start_media_search(
        proposal: AssistantToolProposal,
        *,
        turn_id: str,
        source: IntentProposalSource,
    ) -> None:
        if not accept_intent(turn_id, "files.search_media", source):
            update_chat_busy_state()
            return
        roots = searchable_assistant_roots()
        if not roots:
            chat_window.append_error(
                "Action unavailable: No approved searchable directory is available."
            )
            chat_window.set_busy(False)
            return

        chat_window.set_busy(True)
        thread = AssistantMediaSearchThread(
            assistant_action_bridge,
            proposal,
            roots,
        )
        active_tool_threads.append(thread)

        def handle_result(outcome: MediaSearchOutcome) -> None:
            matches = outcome.matches[:10]
            assistant_tool_result_store.replace(matches)
            ephemeral_action_context.record_selection(
                EphemeralSelectionKind.FILE,
                len(matches),
                allowed_verbs=frozenset(("open", "play")),
            )
            assistant_action_history_window.update_search_results(
                matches,
                summary=f"Found {len(matches)} matching media file(s).",
            )
            refresh_assistant_action_history_window()
            if not matches:
                chat_window.append_message(
                    config.personality.character_name,
                    "I could not find matching audio or video in the approved "
                    "directories.",
                )
                return
            if len(matches) == 1:
                selected = matches[0]
                chat_window.append_message(
                    config.personality.character_name,
                    f"I found {selected.name}.",
                )
                request = ActionRequest(
                    correlation_id=f"llm-media-open-{uuid4().hex}",
                    action_id=OPEN_FILE_ACTION,
                    source="llm_proposal",
                    parameters={"path": selected.path},
                )
                start_action_thread(request)
                return

            lines = [
                f"{index}. {match.name}"
                for index, match in enumerate(matches[:10], start=1)
            ]
            chat_window.append_message(
                config.personality.character_name,
                "I found several matching media files:\n"
                + "\n".join(lines)
                + '\nSay "Play result 1" with the number you want.',
            )
            show_assistant_action_history()

        def handle_failure(error_message: str) -> None:
            logger.error("AI-assisted media search failed: %s", error_message)
            chat_window.append_error(
                "Akiha could not complete the approved media search."
            )

        def handle_cancelled() -> None:
            chat_window.append_notice("Media search stopped.")

        def cleanup_thread() -> None:
            if thread in active_tool_threads:
                active_tool_threads.remove(thread)
            update_chat_busy_state()
            thread.deleteLater()

        thread.result_ready.connect(handle_result)
        thread.failed.connect(handle_failure)
        thread.cancelled.connect(handle_cancelled)
        thread.finished.connect(cleanup_thread)
        thread.start()

    def start_tool_proposal(message: str, *, turn_id: str) -> None:
        chat_window.set_busy(True)
        thread = AssistantToolProposalThread(
            assistant_tool_gateway,
            message,
        )
        active_tool_threads.append(thread)

        def handle_proposal(proposal: AssistantToolProposal) -> None:
            if proposal.kind is AssistantToolKind.NONE:
                start_chat_response(message)
                return
            if proposal.kind is AssistantToolKind.CLARIFY:
                chat_window.append_message(
                    config.personality.character_name,
                    render_assistant_tool_clarification(proposal),
                )
                return
            if proposal.kind is AssistantToolKind.LAUNCH_APPLICATION:
                request = ActionRequest(
                    correlation_id=f"llm-app-{uuid4().hex}",
                    action_id=LAUNCH_APPLICATION_ACTION,
                    source="llm_proposal",
                    parameters={"application_id": proposal.application_id},
                )
                start_intent_action(
                    request,
                    turn_id=turn_id,
                    source=IntentProposalSource.PROVIDER,
                )
                return
            if proposal.kind is AssistantToolKind.CLOSE_APPLICATION:
                request = ActionRequest(
                    correlation_id=f"llm-app-close-{uuid4().hex}",
                    action_id=CLOSE_APPLICATION_ACTION,
                    source="llm_proposal",
                    parameters={"application_id": proposal.application_id},
                )
                start_intent_action(
                    request,
                    turn_id=turn_id,
                    source=IntentProposalSource.PROVIDER,
                )
                return
            if proposal.kind is AssistantToolKind.OPEN_DIRECTORY:
                start_directory_search(
                    proposal,
                    turn_id=turn_id,
                    source=IntentProposalSource.PROVIDER,
                )
                return
            start_media_search(
                proposal,
                turn_id=turn_id,
                source=IntentProposalSource.PROVIDER,
            )

        def handle_failure(error_message: str) -> None:
            logger.info(
                "AI action proposal was unavailable; using normal chat: %s",
                error_message,
            )
            start_chat_response(message)

        def handle_cancelled() -> None:
            chat_window.append_notice("Action interpretation stopped.")

        def cleanup_thread() -> None:
            if thread in active_tool_threads:
                active_tool_threads.remove(thread)
            update_chat_busy_state()
            thread.deleteLater()

        thread.proposal_ready.connect(handle_proposal)
        thread.failed.connect(handle_failure)
        thread.cancelled.connect(handle_cancelled)
        thread.finished.connect(cleanup_thread)
        thread.start()

    def submit_chat_message(message: str) -> None:
        turn_id = f"intent-turn-{uuid4().hex}"
        refresh_assistant_action_aliases()
        selection_error = None
        action_request = assistant_action_bridge.parse_user_text(message)
        action_source = (
            IntentProposalSource.EXACT
            if action_request is not None
            else IntentProposalSource.CONTEXT
        )
        directory_reference = None
        reference = (
            None
            if action_request is not None
            else ephemeral_action_context.resolve(message)
        )
        if isinstance(reference, ActionRequest):
            action_request = reference
        elif isinstance(reference, EphemeralSelectionReference):
            noun = reference.kind.value.removeprefix("spotify_")
            if reference.selected:
                follow_up = f"{reference.verb} that {noun}"
            else:
                if reference.kind in {
                    EphemeralSelectionKind.FILE,
                    EphemeralSelectionKind.DIRECTORY,
                }:
                    follow_up = f"{reference.verb} result {reference.index}"
                else:
                    follow_up = f"{reference.verb} {noun} result {reference.index}"
            selection_store = {
                EphemeralSelectionKind.SPOTIFY_PLAYLIST: (
                    spotify_playlist_selection_store
                ),
                EphemeralSelectionKind.SPOTIFY_ALBUM: spotify_album_selection_store,
                EphemeralSelectionKind.SPOTIFY_TRACK: spotify_track_selection_store,
                EphemeralSelectionKind.SPOTIFY_ARTIST: spotify_artist_selection_store,
                EphemeralSelectionKind.FILE: assistant_tool_result_store,
                EphemeralSelectionKind.DIRECTORY: assistant_tool_result_store,
            }[reference.kind]
            action_request = selection_store.parse_follow_up(follow_up)
            if action_request is None:
                selection_error = "That recent result is no longer available."
        elif isinstance(reference, EphemeralDirectoryReference):
            directory_reference = AssistantToolProposal(
                kind=AssistantToolKind.OPEN_DIRECTORY,
                directory_name=reference.directory_name,
            )
        elif isinstance(reference, EphemeralReferenceError):
            selection_error = reference.message
        directory_proposal = None
        if directory_reference is not None:
            directory_proposal = directory_reference
        elif action_request is None and selection_error is None:
            directory_proposal = parse_directory_navigation_proposal(
                message,
                has_context=ephemeral_action_context.current_directory is not None,
            )
        chat_window.append_message("You", message)
        if selection_error is not None:
            intent_arbiter.complete_local_routing(turn_id)
            chat_window.append_message(
                config.personality.character_name,
                selection_error,
            )
            return
        if action_request is not None:
            start_intent_action(
                action_request,
                turn_id=turn_id,
                source=action_source,
            )
            return
        if directory_proposal is not None:
            start_directory_search(
                directory_proposal,
                turn_id=turn_id,
                source=IntentProposalSource.CONTEXT,
            )
            return
        if assistant_tool_gateway.enabled and should_request_tool_proposal(message):
            intent_arbiter.complete_local_routing(turn_id)
            start_tool_proposal(message, turn_id=turn_id)
            return
        intent_arbiter.complete_local_routing(turn_id)
        start_chat_response(message)

    def cancel_active_chat() -> None:
        for thread in tuple(active_chat_threads):
            thread.cancel()
        for thread in tuple(active_action_threads):
            thread.cancel()
        for thread in tuple(active_tool_threads):
            thread.cancel()
        event_bus.publish(EventType.VOICE_SPEAK_STOP_REQUESTED)

    def cancel_interruptible_work() -> None:
        for thread in tuple(active_chat_threads):
            if thread not in interrupted_chat_threads:
                interrupted_chat_threads.append(thread)
            thread.cancel()
        for thread in tuple(active_action_threads):
            thread.cancel()
        for thread in tuple(active_tool_threads):
            thread.cancel()

    def has_active_operations() -> bool:
        return bool(active_chat_threads or active_action_threads or active_tool_threads)

    def start_new_chat() -> None:
        if has_active_operations():
            chat_window.append_notice(
                "Stop the current response before starting a new chat."
            )
            return

        asyncio.run(chat_controller.start_new_conversation())
        assistant_translation_controller.cancel(wait_ms=0)
        event_bus.publish(EventType.VOICE_SPEAK_STOP_REQUESTED)
        voice_synthesis_controller.clear_replay()
        assistant_tool_result_store.clear()
        spotify_playlist_selection_store.clear()
        spotify_album_selection_store.clear()
        spotify_artist_selection_store.clear()
        spotify_track_selection_store.clear()
        ephemeral_action_context.clear()
        intent_arbiter.clear()
        chat_window.clear_history()
        chat_window.append_notice("New chat started.")
        chat_window.set_status("Ready")
        logger.info("Started a new chat conversation.")

    def clear_current_chat() -> None:
        if has_active_operations():
            chat_window.append_notice("Stop the current response before clearing chat.")
            return

        asyncio.run(chat_controller.clear_current_conversation())
        assistant_translation_controller.cancel(wait_ms=0)
        event_bus.publish(EventType.VOICE_SPEAK_STOP_REQUESTED)
        voice_synthesis_controller.clear_replay()
        assistant_tool_result_store.clear()
        spotify_playlist_selection_store.clear()
        spotify_album_selection_store.clear()
        spotify_artist_selection_store.clear()
        spotify_track_selection_store.clear()
        ephemeral_action_context.clear()
        intent_arbiter.clear()
        chat_window.clear_history()
        chat_window.append_notice("Chat cleared.")
        chat_window.set_status("Ready")
        logger.info("Cleared current chat conversation.")

    def export_current_chat(selected_path: str) -> None:
        if has_active_operations():
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
    talk_interruption_controller = TalkInterruptionController(
        event_bus=event_bus,
        voice_controller=voice_controller,
        has_interruptible_work=has_active_operations,
        cancel_interruptible_work=cancel_interruptible_work,
    )
    local_conversation_session_controller = LocalConversationSessionController(
        event_bus=event_bus,
        voice_controller=voice_controller,
        session_coordinator=voice_session_coordinator,
        processing_mode_provider=current_voice_processing_mode,
        has_interruptible_work=has_active_operations,
        cancel_interruptible_work=cancel_interruptible_work,
    )

    def present_local_conversation_state(event: Event) -> None:
        elapsed = event.payload.get("elapsed_seconds")
        reason = event.payload.get("reason")
        chat_window.set_voice_conversation_state(
            active=event.payload.get("active") is True,
            elapsed_seconds=(
                elapsed if isinstance(elapsed, int) and elapsed >= 0 else 0
            ),
            reason=reason if isinstance(reason, str) else "",
        )

    event_bus.subscribe(
        EventType.VOICE_CONVERSATION_STATE_CHANGED,
        present_local_conversation_state,
    )
    local_conversation_tick_timer = QTimer()
    local_conversation_tick_timer.setInterval(1_000)
    local_conversation_tick_timer.timeout.connect(
        local_conversation_session_controller.tick
    )
    local_conversation_tick_timer.start()
    chat_window.voice_listen_requested.connect(
        talk_interruption_controller.request_talk
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
    chat_window.voice_conversation_start_requested.connect(
        local_conversation_session_controller.start
    )
    chat_window.voice_conversation_end_requested.connect(
        local_conversation_session_controller.end
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
    settings_window.assistant_action_history_requested.connect(
        show_assistant_action_history
    )
    assistant_action_history_window.clear_requested.connect(
        clear_assistant_action_history
    )
    event_bus.subscribe(EventType.PET_DRAG_ENDED, save_window_position)

    def tick_behavior() -> None:
        activity = activity_controller.tick()
        scheduled_check_in_controller.tick(activity)

    activity_tick_timer = QTimer()
    activity_tick_timer.timeout.connect(tick_behavior)
    activity_tick_timer.start(30_000)

    def shutdown_app() -> None:
        local_conversation_tick_timer.stop()
        voice_endpoint_controller.cancel()
        local_conversation_session_controller.close()
        push_to_talk_session_controller.close()
        ai_discovery_stopped = settings_window.cancel_ai_discovery()
        if not ai_discovery_stopped:
            logger.warning("AI provider discovery did not stop before shutdown.")
        spotify_authorization_stopped = settings_window.cancel_spotify_authorization()
        if not spotify_authorization_stopped:
            logger.warning("Spotify authorization did not stop before shutdown.")
        translations_stopped = assistant_translation_controller.cancel()
        if not translations_stopped:
            logger.warning("Assistant translation did not stop before shutdown.")
        active_runtime_threads = [
            *active_chat_threads,
            *active_action_threads,
            *active_tool_threads,
        ]
        try:
            streaming_voice_output_controller.cancel()
        except Exception:
            logger.exception("Streaming voice output did not stop before shutdown.")
        result = shutdown_runtime(
            activity_timer=activity_tick_timer,
            active_chat_threads=active_runtime_threads,
            save_window_position=save_window_position,
            logger=logger,
            voice_capture=voice_capture_controller,
            voice_diagnostics=voice_diagnostics_controller,
            voice_transcription=voice_transcription_controller,
            voice_synthesis=voice_synthesis_controller,
            voice_playback=voice_playback_controller,
            voice_engine=voicevox_engine_manager,
        )
        logger.info(
            "Shutdown cleanup complete: position_saved=%s, timer_stopped=%s, "
            "cancelled_threads=%s, unfinished_threads=%s, "
            "voice_capture_stopped=%s, voice_diagnostics_stopped=%s, "
            "voice_transcription_stopped=%s, "
            "voice_synthesis_stopped=%s, voice_playback_stopped=%s, "
            "voice_engine_stopped=%s, "
            "ai_discovery_stopped=%s, spotify_authorization_stopped=%s, "
            "translations_stopped=%s.",
            result.position_saved,
            result.timer_stopped,
            result.cancelled_threads,
            result.unfinished_threads,
            result.voice_capture_stopped,
            result.voice_diagnostics_stopped,
            result.voice_transcription_stopped,
            result.voice_synthesis_stopped,
            result.voice_playback_stopped,
            result.voice_engine_stopped,
            ai_discovery_stopped,
            spotify_authorization_stopped,
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
    if privacy_notice_required(config.privacy):
        QTimer.singleShot(0, privacy_notice.show)
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
        action_repository,
        assistant_action_history_window,
        assistant_action_bridge,
        assistant_action_service,
        assistant_translation_controller,
        chat_controller,
        activity_controller,
        activity_tick_timer,
        active_chat_threads,
        active_action_threads,
        active_tool_threads,
        assistant_tool_gateway,
        assistant_tool_result_store,
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
        privacy_notice,
        proactive_controller,
        proactive_delivery_controller,
        proactive_speech_controller,
        scheduled_check_in_controller,
        scheduled_check_in_engine,
        settings_window,
        spotify_client,
        spotify_device_coordinator,
        spotify_session,
        tray_icon,
        user_config_store,
        voice_capture_controller,
        voice_controller,
        voice_diagnostics_controller,
        voice_endpoint_controller,
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


def _collapse_nested_roots(roots: tuple[str, ...]) -> tuple[str, ...]:
    """Remove duplicate and nested roots to avoid repeating the same search."""
    retained: list[tuple[str, str]] = []
    candidates = sorted(
        roots,
        key=lambda root: (
            len(os.path.normcase(os.path.abspath(root))),
            os.path.normcase(os.path.abspath(root)),
        ),
    )
    for root in candidates:
        normalized = os.path.normcase(os.path.abspath(root))
        if any(
            normalized == parent
            or normalized.startswith(parent.rstrip(os.sep) + os.sep)
            for _, parent in retained
        ):
            continue
        retained.append((root, normalized))
    return tuple(root for root, _ in retained)


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
