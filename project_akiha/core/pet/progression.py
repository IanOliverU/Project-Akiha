"""Pure progression, cooldown, and anti-farming reward rules."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from project_akiha.core.pet.models import (
    CARE_REWARD_CURRENCY,
    CARE_REWARD_XP,
    CONVERSATION_REWARD_XP,
    CareAction,
    PetInteractionEvent,
    PetInteractionKind,
    PetProgression,
    PetRewardDecision,
    PetRewardGrant,
    PetRewardKind,
    PetRewardOutcome,
    level_for_xp,
)

CARE_REWARD_COOLDOWN = timedelta(minutes=30)
CARE_REWARD_DAILY_CAP = 12
CONVERSATION_REWARD_COOLDOWN = timedelta(minutes=10)
CONVERSATION_REWARD_DAILY_CAP = 12
REWARD_ROLLING_WINDOW = timedelta(hours=24)

_CARE_REWARD_KINDS = frozenset(
    {
        PetRewardKind.CARE_FEED,
        PetRewardKind.CARE_REST,
        PetRewardKind.CARE_SPEND_TIME,
    }
)


def evaluate_care_reward(
    progression: PetProgression,
    action: CareAction,
    *,
    care_changed: bool,
    recent_grants: tuple[PetRewardGrant, ...],
    granted_at: datetime,
) -> PetRewardOutcome:
    """Evaluate one care reward without mutating care eligibility itself."""
    _require_progression(progression)
    if not isinstance(action, CareAction):
        raise TypeError("action must be a CareAction value.")
    if not isinstance(care_changed, bool):
        raise TypeError("care_changed must be a boolean.")
    grants = _require_grants(recent_grants)
    now = _require_aware_datetime(granted_at, "granted_at")
    kind = reward_kind_for_care_action(action)

    if not care_changed:
        return _denied_outcome(
            progression,
            kind,
            PetRewardDecision.NO_STATE_CHANGE,
        )

    care_grants = _within_rolling_window(grants, now, _CARE_REWARD_KINDS)
    same_kind = tuple(grant for grant in care_grants if grant.kind is kind)
    if _cooldown_active(same_kind, now, CARE_REWARD_COOLDOWN):
        return _denied_outcome(progression, kind, PetRewardDecision.COOLDOWN)
    if len(care_grants) >= CARE_REWARD_DAILY_CAP:
        return _denied_outcome(progression, kind, PetRewardDecision.DAILY_CAP)

    return _granted_outcome(
        progression,
        PetRewardGrant(
            kind=kind,
            event_id=None,
            xp_awarded=CARE_REWARD_XP,
            currency_awarded=CARE_REWARD_CURRENCY,
            granted_at=now,
        ),
    )


def evaluate_interaction_reward(
    progression: PetProgression,
    event: PetInteractionEvent,
    *,
    event_already_rewarded: bool,
    recent_grants: tuple[PetRewardGrant, ...],
    granted_at: datetime,
) -> PetRewardOutcome:
    """Evaluate one structured interaction reward and event deduplication."""
    _require_progression(progression)
    if not isinstance(event, PetInteractionEvent):
        raise TypeError("event must be a PetInteractionEvent value.")
    if not isinstance(event_already_rewarded, bool):
        raise TypeError("event_already_rewarded must be a boolean.")
    grants = _require_grants(recent_grants)
    now = _require_aware_datetime(granted_at, "granted_at")
    if event.kind is not PetInteractionKind.CONVERSATION_COMPLETED:
        raise TypeError("event kind is not reward eligible.")
    kind = PetRewardKind.CONVERSATION_COMPLETED

    if event_already_rewarded:
        return _denied_outcome(
            progression,
            kind,
            PetRewardDecision.DUPLICATE_EVENT,
        )

    conversation_grants = _within_rolling_window(grants, now, frozenset({kind}))
    if _cooldown_active(
        conversation_grants,
        now,
        CONVERSATION_REWARD_COOLDOWN,
    ):
        return _denied_outcome(progression, kind, PetRewardDecision.COOLDOWN)
    if len(conversation_grants) >= CONVERSATION_REWARD_DAILY_CAP:
        return _denied_outcome(progression, kind, PetRewardDecision.DAILY_CAP)

    return _granted_outcome(
        progression,
        PetRewardGrant(
            kind=kind,
            event_id=event.event_id,
            xp_awarded=CONVERSATION_REWARD_XP,
            currency_awarded=0,
            granted_at=now,
        ),
    )


def reward_kind_for_care_action(action: CareAction) -> PetRewardKind:
    """Map one closed care enum to its closed reward-ledger kind."""
    if action is CareAction.FEED:
        return PetRewardKind.CARE_FEED
    if action is CareAction.REST:
        return PetRewardKind.CARE_REST
    if action is CareAction.SPEND_TIME:
        return PetRewardKind.CARE_SPEND_TIME
    raise TypeError("action must be a CareAction value.")


def _granted_outcome(
    progression: PetProgression,
    grant: PetRewardGrant,
) -> PetRewardOutcome:
    xp = progression.xp + grant.xp_awarded
    current = replace(
        progression,
        xp=xp,
        level=level_for_xp(xp),
        currency=progression.currency + grant.currency_awarded,
    )
    return PetRewardOutcome(
        kind=grant.kind,
        decision=PetRewardDecision.GRANTED,
        previous_progression=progression,
        current_progression=current,
        grant=grant,
    )


def _denied_outcome(
    progression: PetProgression,
    kind: PetRewardKind,
    decision: PetRewardDecision,
) -> PetRewardOutcome:
    return PetRewardOutcome(
        kind=kind,
        decision=decision,
        previous_progression=progression,
        current_progression=progression,
    )


def _within_rolling_window(
    grants: tuple[PetRewardGrant, ...],
    now: datetime,
    kinds: frozenset[PetRewardKind],
) -> tuple[PetRewardGrant, ...]:
    current = _require_aware_datetime(now, "now")
    start = current - REWARD_ROLLING_WINDOW
    return tuple(
        grant for grant in grants if grant.kind in kinds and grant.granted_at > start
    )


def _cooldown_active(
    grants: tuple[PetRewardGrant, ...],
    now: datetime,
    cooldown: timedelta,
) -> bool:
    current = _require_aware_datetime(now, "now")
    return any(current - grant.granted_at < cooldown for grant in grants)


def _require_progression(progression: object) -> None:
    if not isinstance(progression, PetProgression):
        raise TypeError("progression must be a PetProgression value.")


def _require_grants(value: object) -> tuple[PetRewardGrant, ...]:
    if not isinstance(value, tuple) or any(
        not isinstance(grant, PetRewardGrant) for grant in value
    ):
        raise TypeError("recent_grants must be a tuple of PetRewardGrant values.")
    return value


def _require_aware_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")
    return value
