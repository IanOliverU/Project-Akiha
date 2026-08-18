"""Structured Phase 9 pet-care reaction orchestration."""

from __future__ import annotations

from collections.abc import Callable

from project_akiha.app.assistant_speech_controller import AssistantSpeechController
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.pet import PetCareEvaluation
from project_akiha.services.speech_identity import pet_care_speech_line


class PetReactionController:
    """Publish and present reactions from committed typed care outcomes."""

    def __init__(
        self,
        event_bus: EventBus,
        speech_controller: AssistantSpeechController,
        *,
        line_provider: Callable[..., str | None] = pet_care_speech_line,
    ) -> None:
        self._event_bus = event_bus
        self._speech_controller = speech_controller
        self._line_provider = line_provider
        event_bus.subscribe(EventType.PET_CARE_COMPLETED, self._handle_care_completed)

    def publish_care_evaluation(self, evaluation: PetCareEvaluation) -> None:
        """Publish sanitized reaction events from one durable care result."""
        if not isinstance(evaluation, PetCareEvaluation):
            raise TypeError("evaluation must be a PetCareEvaluation value.")

        outcome = evaluation.care_outcome
        if not outcome.changed:
            return
        previous_affection = outcome.previous_state.wellbeing.affection
        current_affection = outcome.current_state.wellbeing.affection
        previous_level = evaluation.reward_outcome.previous_progression.level
        current_level = evaluation.reward_outcome.current_progression.level
        level_increased = current_level > previous_level

        self._event_bus.publish(
            EventType.PET_CARE_COMPLETED,
            {
                "kind": f"pet_care_{outcome.action.value}_completed",
                "action": outcome.action.value,
                "changed": True,
                "reward_granted": evaluation.reward_outcome.granted,
                "level_increased": level_increased,
            },
        )
        if current_affection > previous_affection:
            self._event_bus.publish(
                EventType.PET_AFFECTION_INCREASED,
                {
                    "kind": "pet_affection_increased",
                    "previous_value": previous_affection,
                    "current_value": current_affection,
                    "source": outcome.action.value,
                },
            )
        if level_increased:
            self._event_bus.publish(
                EventType.PET_LEVEL_INCREASED,
                {
                    "kind": "pet_level_increased",
                    "previous_level": previous_level,
                    "current_level": current_level,
                    "source": outcome.action.value,
                },
            )

    def _handle_care_completed(self, event: Event) -> None:
        if event.payload.get("changed") is not True:
            return
        action = event.payload.get("action")
        level_increased = event.payload.get("level_increased")
        if not isinstance(action, str) or not isinstance(level_increased, bool):
            return
        line = self._line_provider(action, level_increased=level_increased)
        if line is not None:
            self._speech_controller.submit_pet_reaction(line)
