"""Tests for structured pet voice and presentation reactions."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from project_akiha.app.assistant_speech_controller import AssistantSpeechController
from project_akiha.app.pet_reaction_controller import PetReactionController
from project_akiha.app.voice_controller import VoiceController
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.pet import (
    CareAction,
    PetCareEvaluation,
    PetProgression,
    PetRewardGrant,
    PetRewardKind,
    PetState,
    PetStateRecord,
    PetWellbeing,
    apply_care_action,
    evaluate_care_reward,
)


class PetReactionControllerTest(unittest.TestCase):
    """Verify committed typed care outcomes produce bounded reactions."""

    def test_spend_time_publishes_care_affection_and_level_events(self) -> None:
        bus, controller, speech_requests = _controller()
        care_events: list[Event] = []
        affection_events: list[Event] = []
        level_events: list[Event] = []
        bus.subscribe(EventType.PET_CARE_COMPLETED, care_events.append)
        bus.subscribe(EventType.PET_AFFECTION_INCREASED, affection_events.append)
        bus.subscribe(EventType.PET_LEVEL_INCREASED, level_events.append)

        controller.publish_care_evaluation(_level_up_evaluation())

        self.assertEqual(care_events[0].payload["action"], "spend_time")
        self.assertTrue(care_events[0].payload["level_increased"])
        self.assertEqual(affection_events[0].payload["previous_value"], 50)
        self.assertEqual(affection_events[0].payload["current_value"], 51)
        self.assertEqual(level_events[0].payload["previous_level"], 1)
        self.assertEqual(level_events[0].payload["current_level"], 2)
        self.assertEqual(speech_requests[0].payload["source"], "pet_reaction")

    def test_voice_setting_can_suppress_pet_reaction_without_events(self) -> None:
        bus, controller, speech_requests = _controller(automatic_speech=False)
        care_events: list[Event] = []
        bus.subscribe(EventType.PET_CARE_COMPLETED, care_events.append)

        controller.publish_care_evaluation(_level_up_evaluation())

        self.assertEqual(len(care_events), 1)
        self.assertEqual(speech_requests, [])

    def test_no_op_care_does_not_publish_or_speak(self) -> None:
        bus, controller, speech_requests = _controller()
        care_events: list[Event] = []
        bus.subscribe(EventType.PET_CARE_COMPLETED, care_events.append)

        controller.publish_care_evaluation(_no_op_evaluation())

        self.assertEqual(care_events, [])
        self.assertEqual(speech_requests, [])

    def test_rejects_untyped_evaluation(self) -> None:
        _, controller, _ = _controller()

        with self.assertRaises(TypeError):
            controller.publish_care_evaluation(  # type: ignore[arg-type]
                {"dialogue": "Akiha is hungry"}
            )


def _controller(
    *,
    automatic_speech: bool = True,
) -> tuple[EventBus, PetReactionController, list[Event]]:
    bus = EventBus()
    config = VoiceConfig(enabled=True, automatic_speech_enabled=automatic_speech)
    speech = AssistantSpeechController(bus, VoiceController(bus, config), config)
    requests: list[Event] = []
    bus.subscribe(EventType.VOICE_SPEAK_REQUESTED, requests.append)
    controller = PetReactionController(bus, speech)
    return bus, controller, requests


def _level_up_evaluation() -> PetCareEvaluation:
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    previous = PetState(
        wellbeing=PetWellbeing(attention=50, affection=50),
        progression=PetProgression(xp=20, level=1, currency=0),
    )
    care = apply_care_action(previous, CareAction.SPEND_TIME)
    reward = evaluate_care_reward(
        previous.progression,
        CareAction.SPEND_TIME,
        care_changed=care.changed,
        recent_grants=(),
        granted_at=now,
    )
    grant = reward.grant
    assert isinstance(grant, PetRewardGrant)
    assert grant.kind is PetRewardKind.CARE_SPEND_TIME
    record = PetStateRecord(
        state=PetState(
            wellbeing=care.current_state.wellbeing,
            progression=reward.current_progression,
            decay_progress=care.current_state.decay_progress,
        ),
        revision=1,
        evaluated_at=now,
        created_at=now,
        updated_at=now,
    )
    return PetCareEvaluation(
        record=record,
        care_outcome=care,
        reward_outcome=reward,
    )


def _no_op_evaluation() -> PetCareEvaluation:
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    previous = PetState(wellbeing=PetWellbeing(satiety=100))
    care = apply_care_action(previous, CareAction.FEED)
    reward = evaluate_care_reward(
        previous.progression,
        CareAction.FEED,
        care_changed=care.changed,
        recent_grants=(),
        granted_at=now,
    )
    return PetCareEvaluation(
        record=PetStateRecord(
            state=previous,
            revision=0,
            evaluated_at=now,
            created_at=now,
            updated_at=now,
        ),
        care_outcome=care,
        reward_outcome=reward,
    )


if __name__ == "__main__":
    unittest.main()
