"""Phase 4 behavior primitives for activity-aware companion features."""

from project_akiha.core.behavior.activity import (
    ActivitySnapshot,
    ActivityState,
    ActivityTracker,
)
from project_akiha.core.behavior.notification_policy import (
    NotificationDecision,
    NotificationPolicy,
    NotificationRequest,
    NotificationUrgency,
)
from project_akiha.core.behavior.proactive import (
    ProactiveSuggestion,
    ProactiveSuggestionEngine,
)

__all__ = [
    "ActivitySnapshot",
    "ActivityState",
    "ActivityTracker",
    "NotificationDecision",
    "NotificationPolicy",
    "NotificationRequest",
    "NotificationUrgency",
    "ProactiveSuggestion",
    "ProactiveSuggestionEngine",
]
