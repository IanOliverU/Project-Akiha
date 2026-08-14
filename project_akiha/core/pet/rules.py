"""Pure, clock-independent rules for elapsed pet-state decay."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import timedelta

from project_akiha.core.pet.models import (
    DecayMode,
    DecayStatus,
    PetBandTransition,
    PetDecayOutcome,
    PetDecayPolicy,
    PetDecayProgress,
    PetNeed,
    PetState,
    WellbeingBand,
    wellbeing_band,
)

DEFAULT_DECAY_POLICY = PetDecayPolicy()

_BANDS_BY_RANK = (
    WellbeingBand.CRITICAL,
    WellbeingBand.LOW,
    WellbeingBand.STABLE,
)


def evaluate_elapsed_decay(
    state: PetState,
    elapsed: timedelta,
    *,
    mode: DecayMode = DecayMode.RUNTIME,
    policy: PetDecayPolicy = DEFAULT_DECAY_POLICY,
) -> PetDecayOutcome:
    """Apply elapsed seconds without consulting a clock or external service."""
    if not isinstance(state, PetState):
        raise TypeError("state must be a PetState value.")
    if not isinstance(elapsed, timedelta):
        raise TypeError("elapsed must be a timedelta value.")
    if not isinstance(mode, DecayMode):
        raise TypeError("mode must be a DecayMode value.")
    if not isinstance(policy, PetDecayPolicy):
        raise TypeError("policy must be a PetDecayPolicy value.")

    requested_seconds = math.floor(elapsed.total_seconds())
    if requested_seconds < 0:
        return _unchanged_outcome(
            state,
            mode=mode,
            status=DecayStatus.CLOCK_ROLLBACK,
            requested_seconds=requested_seconds,
        )
    if requested_seconds == 0:
        return _unchanged_outcome(
            state,
            mode=mode,
            status=DecayStatus.NO_ELAPSED_TIME,
            requested_seconds=0,
        )

    applied_seconds = requested_seconds
    was_capped = False
    if mode is DecayMode.OFFLINE_CATCH_UP:
        applied_seconds = min(requested_seconds, policy.offline_cap_seconds)
        was_capped = applied_seconds != requested_seconds

    satiety, satiety_remainder = _decay_value(
        state.wellbeing.satiety,
        state.decay_progress.satiety_seconds,
        elapsed_seconds=applied_seconds,
        interval_seconds=policy.satiety_interval_seconds,
    )
    energy, energy_remainder = _decay_value(
        state.wellbeing.energy,
        state.decay_progress.energy_seconds,
        elapsed_seconds=applied_seconds,
        interval_seconds=policy.energy_interval_seconds,
    )
    attention, attention_remainder = _decay_value(
        state.wellbeing.attention,
        state.decay_progress.attention_seconds,
        elapsed_seconds=applied_seconds,
        interval_seconds=policy.attention_interval_seconds,
    )

    current_wellbeing = replace(
        state.wellbeing,
        satiety=satiety,
        energy=energy,
        attention=attention,
    )
    current_state = replace(
        state,
        wellbeing=current_wellbeing,
        decay_progress=PetDecayProgress(
            satiety_seconds=satiety_remainder,
            energy_seconds=energy_remainder,
            attention_seconds=attention_remainder,
        ),
    )
    transitions = tuple(
        transition
        for need in PetNeed
        for transition in collect_band_transitions(
            need,
            state.wellbeing.value_for(need),
            current_wellbeing.value_for(need),
        )
    )
    return PetDecayOutcome(
        previous_state=state,
        current_state=current_state,
        mode=mode,
        status=DecayStatus.APPLIED,
        requested_elapsed_seconds=requested_seconds,
        applied_elapsed_seconds=applied_seconds,
        was_capped=was_capped,
        band_transitions=transitions,
    )


def collect_band_transitions(
    need: PetNeed,
    previous_value: int,
    current_value: int,
) -> tuple[PetBandTransition, ...]:
    """Return each adjacent threshold edge crossed between two values."""
    if not isinstance(need, PetNeed):
        raise TypeError("need must be a PetNeed value.")
    previous_band = wellbeing_band(previous_value)
    current_band = wellbeing_band(current_value)
    previous_rank = _BANDS_BY_RANK.index(previous_band)
    current_rank = _BANDS_BY_RANK.index(current_band)
    if previous_rank == current_rank:
        return ()

    direction = 1 if current_rank > previous_rank else -1
    transitions = []
    rank = previous_rank
    while rank != current_rank:
        next_rank = rank + direction
        transitions.append(
            PetBandTransition(
                need=need,
                previous_band=_BANDS_BY_RANK[rank],
                current_band=_BANDS_BY_RANK[next_rank],
            )
        )
        rank = next_rank
    return tuple(transitions)


def _decay_value(
    value: int,
    remainder_seconds: int,
    *,
    elapsed_seconds: int,
    interval_seconds: int,
) -> tuple[int, int]:
    if value == 0:
        return 0, 0
    decay_steps, remainder = divmod(
        remainder_seconds + elapsed_seconds,
        interval_seconds,
    )
    current_value = max(0, value - decay_steps)
    if current_value == 0:
        remainder = 0
    return current_value, remainder


def _unchanged_outcome(
    state: PetState,
    *,
    mode: DecayMode,
    status: DecayStatus,
    requested_seconds: int,
) -> PetDecayOutcome:
    return PetDecayOutcome(
        previous_state=state,
        current_state=state,
        mode=mode,
        status=status,
        requested_elapsed_seconds=requested_seconds,
        applied_elapsed_seconds=0,
        was_capped=False,
    )
