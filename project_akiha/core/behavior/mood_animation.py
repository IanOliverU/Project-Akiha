"""Map companion mood states to pet animation requests."""

from __future__ import annotations

from dataclasses import dataclass

from project_akiha.core.behavior.mood import CompanionMood
from project_akiha.core.state.animation import AnimationState


@dataclass(frozen=True, slots=True)
class MoodAnimationDecision:
    """A mood-driven animation request, or a no-op reason."""

    animation_state: AnimationState | None
    reason: str
    mood_driven_sleep: bool = False


class MoodAnimationMapper:
    """Choose safe animation requests from mood and current animation state."""

    def decide(
        self,
        *,
        mood: CompanionMood,
        current_animation_state: AnimationState,
        sleeping_from_mood: bool,
    ) -> MoodAnimationDecision:
        """Return the animation request implied by the mood, if any."""
        if mood == CompanionMood.RESTING:
            if current_animation_state == AnimationState.IDLE:
                return MoodAnimationDecision(
                    animation_state=AnimationState.SLEEPING,
                    reason="mood_resting",
                    mood_driven_sleep=True,
                )
            return MoodAnimationDecision(
                animation_state=None,
                reason="busy",
            )

        if sleeping_from_mood and current_animation_state == AnimationState.SLEEPING:
            if mood in {
                CompanionMood.ATTENTIVE,
                CompanionMood.CHECKING_IN,
                CompanionMood.WAITING,
                CompanionMood.CALM,
            }:
                return MoodAnimationDecision(
                    animation_state=AnimationState.IDLE,
                    reason=f"mood_{mood.value}",
                )

        return MoodAnimationDecision(animation_state=None, reason="no_change")
