"""Canonical event names used across Project Akiha."""

from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
    """Known event types for the application event bus."""

    PET_DRAG_STARTED = "pet.drag_started"
    PET_DRAGGED = "pet.dragged"
    PET_DRAG_ENDED = "pet.drag_ended"
    PET_WALK_REQUESTED = "pet.walk_requested"
    PET_IDLE_REQUESTED = "pet.idle_requested"
    PET_SLEEP_REQUESTED = "pet.sleep_requested"
    PET_WAKE_REQUESTED = "pet.wake_requested"
    CHAT_OPEN_REQUESTED = "chat.open_requested"
    SETTINGS_OPEN_REQUESTED = "settings.open_requested"
    BEHAVIOR_HISTORY_OPEN_REQUESTED = "behavior_history.open_requested"
    APP_QUIT_REQUESTED = "app.quit_requested"
    USER_ACTIVITY_OBSERVED = "activity.observed"
    USER_ACTIVITY_STATE_CHANGED = "activity.state_changed"
    PROACTIVE_SUGGESTION_READY = "proactive.suggestion_ready"
    PROACTIVE_SUGGESTION_DELIVERED = "proactive.suggestion_delivered"
    MOOD_STATE_CHANGED = "mood.state_changed"
    VOICE_LISTEN_REQUESTED = "voice.listen_requested"
    VOICE_LISTEN_STOP_REQUESTED = "voice.listen_stop_requested"
    VOICE_LISTEN_CANCEL_REQUESTED = "voice.listen_cancel_requested"
    VOICE_SPEAK_REQUESTED = "voice.speak_requested"
    VOICE_SPEAK_STOP_REQUESTED = "voice.speak_stop_requested"
    VOICE_REPLAY_REQUESTED = "voice.replay_requested"
    VOICE_REPLAY_AVAILABILITY_CHANGED = "voice.replay_availability_changed"
    VOICE_MICROPHONE_TEST_COMPLETED = "voice.microphone_test_completed"
    VOICE_MICROPHONE_ACTIVITY_UPDATED = "voice.microphone_activity_updated"
    VOICE_TRANSCRIPT_PARTIAL = "voice.transcript_partial"
    VOICE_TRANSCRIPT_READY = "voice.transcript_ready"
    VOICE_STATE_CHANGED = "voice.state_changed"
    VOICE_CONVERSATION_STATE_CHANGED = "voice.conversation_state_changed"
    VOICE_ERROR_OCCURRED = "voice.error_occurred"
    STATE_CHANGED = "state.changed"
    ERROR_OCCURRED = "error.occurred"
