"""Pure, language-neutral rules for explicit pet care actions."""

from __future__ import annotations

from dataclasses import replace

from project_akiha.core.pet.models import (
    CareAction,
    PetCareOutcome,
    PetNeed,
    PetState,
)
from project_akiha.core.pet.rules import collect_band_transitions

_FEED_SATIETY_GAIN = 25
_REST_ENERGY_GAIN = 25
_SPEND_TIME_ATTENTION_GAIN = 20
_SPEND_TIME_AFFECTION_GAIN = 1
_MAXIMUM_WELLBEING = 100


def apply_care_action(state: PetState, action: CareAction) -> PetCareOutcome:
    """Apply one approved care action without clocks, persistence, or rewards."""
    if not isinstance(state, PetState):
        raise TypeError("state must be a PetState value.")
    if not isinstance(action, CareAction):
        raise TypeError("action must be a CareAction value.")

    if action is CareAction.FEED:
        current_wellbeing = replace(
            state.wellbeing,
            satiety=_clamp_gain(
                state.wellbeing.satiety,
                _FEED_SATIETY_GAIN,
            ),
        )
        affected_needs = (PetNeed.SATIETY,)
    elif action is CareAction.REST:
        current_wellbeing = replace(
            state.wellbeing,
            energy=_clamp_gain(
                state.wellbeing.energy,
                _REST_ENERGY_GAIN,
            ),
        )
        affected_needs = (PetNeed.ENERGY,)
    elif action is CareAction.SPEND_TIME:
        current_wellbeing = replace(
            state.wellbeing,
            attention=_clamp_gain(
                state.wellbeing.attention,
                _SPEND_TIME_ATTENTION_GAIN,
            ),
            affection=_clamp_gain(
                state.wellbeing.affection,
                _SPEND_TIME_AFFECTION_GAIN,
            ),
        )
        affected_needs = (PetNeed.ATTENTION,)
    else:
        raise TypeError("action must be a CareAction value.")

    current_state = replace(state, wellbeing=current_wellbeing)
    transitions = tuple(
        transition
        for need in affected_needs
        for transition in collect_band_transitions(
            need,
            state.wellbeing.value_for(need),
            current_wellbeing.value_for(need),
        )
    )
    return PetCareOutcome(
        action=action,
        previous_state=state,
        current_state=current_state,
        band_transitions=transitions,
    )


def _clamp_gain(value: int, gain: int) -> int:
    return min(_MAXIMUM_WELLBEING, value + gain)
