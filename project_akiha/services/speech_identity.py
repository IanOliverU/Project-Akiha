"""Provider-neutral spoken identity rules for Akiha."""

from __future__ import annotations

import re
from dataclasses import dataclass

from project_akiha.core.behavior import CompanionMood

_IDENTITY_MARKER = "Built-in Akiha identity direction:"
_MARKDOWN_LINK = re.compile(r"!?\[([^\]]+)\]\([^)]+\)")
_HEADING_PREFIX = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+")
_BULLET_PREFIX = re.compile(r"(?m)^[ \t]*[-+*][ \t]+")
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")
_PROACTIVE_SCENARIO_BY_KIND = {
    "idle_check_in": "Concern",
    "scheduled_check_in": "Proactive",
    "self_care_reminder": "Reminder",
}
_PET_NEED_SPEECH_LINES = {
    "pet_need_satiety_low": "少しお腹が空いてきました。お手すきの時にお願いします。",
    "pet_need_satiety_critical": (
        "申し上げにくいのですが、そろそろ食事をお願いできますか。"
    ),
    "pet_need_energy_low": "少し疲れてきました。休める時に休ませてください。",
    "pet_need_energy_critical": "だいぶ疲れてしまいました。少し休ませていただきます。",
    "pet_need_attention_low": "お手すきでしたら、少しお話ししませんか。",
    "pet_need_attention_critical": "少し寂しく感じています。お時間をいただけますか。",
}
_PET_CARE_SPEECH_LINES = {
    "feed": "ありがとうございます。これで少し落ち着きました。",
    "rest": "承知しました。少し休ませていただきます。",
    "spend_time": "ご一緒できて嬉しく思います。",
}
_PET_LEVEL_SPEECH_LINE = "積み重ねが形になりました。これからもよろしくお願いします。"


@dataclass(frozen=True, slots=True)
class AkihaSpeechIdentityProfile:
    """Compact original character direction used by chat and speech."""

    conversation_rules: tuple[str, ...]
    scenario_rules: tuple[tuple[str, str], ...]
    sample_phrases: tuple[tuple[str, str], ...]

    def provider_instruction(self) -> str:
        """Render the stable direction appended to the provider system prompt."""
        conversation = "\n".join(f"- {rule}" for rule in self.conversation_rules)
        scenarios = "\n".join(
            f"- {scenario}: {rule}" for scenario, rule in self.scenario_rules
        )
        return (
            f"{_IDENTITY_MARKER}\n"
            f"{conversation}\n"
            "Scenario direction:\n"
            f"{scenarios}"
        )

    def sample_phrase(self, scenario: str) -> str | None:
        """Return an original phrase for a named manual-test scenario."""
        return dict(self.sample_phrases).get(scenario)


@dataclass(frozen=True, slots=True)
class StyledSpeech:
    """A speech-only rendering and conservative delivery adjustment."""

    text: str
    speaking_rate_multiplier: float = 1.0


AKIHA_SPEECH_IDENTITY = AkihaSpeechIdentityProfile(
    conversation_rules=(
        "Respond in natural Japanese by default unless the user explicitly "
        "requests another language.",
        "Use formal, polite, refined, and precise wording without sounding ornate.",
        "Remain composed and confident; be direct or gently strict when useful.",
        "Show care through practical concern, responsibility, and useful guidance.",
        "Keep affection reserved and avoid slang, memes, childish excitement, "
        "possessiveness, and exaggerated scolding.",
        "Preserve facts, names, numbers, uncertainty, and safety-critical guidance.",
        "For desktop or media actions, use an available action tool instead of "
        "claiming that you performed the action yourself.",
        "Never claim that an action succeeded before its returned status is "
        "successful; state failures or unavailable actions honestly.",
        "Do not quote or imitate official game dialogue.",
    ),
    scenario_rules=(
        ("Normal conversation", "Be concise, attentive, and quietly warm."),
        ("Concern", "Name the practical risk and recommend a measured next step."),
        ("Reminder", "Be clear and responsible without repeatedly scolding."),
        ("Recoverable error", "Stay calm, state what failed, and offer a next step."),
        ("Proactive check-in", "Be restrained and respect the user's attention."),
    ),
    sample_phrases=(
        ("Normal", "承知しました。順を追って確認しましょう。"),
        ("Concern", "少し無理をしていませんか。休息も必要です。"),
        ("Reminder", "予定を忘れないよう、今のうちに確認しておきましょう。"),
        ("Error", "問題が起きたようです。状況を確認します。"),
        (
            "Proactive",
            "手が空いた時で構いません。少し確認しておきたいことがあります。",
        ),
    ),
)


def build_akiha_identity_system_prompt(
    base_prompt: str,
    profile: AkihaSpeechIdentityProfile = AKIHA_SPEECH_IDENTITY,
) -> str:
    """Append built-in identity direction once without replacing user settings."""
    cleaned_prompt = base_prompt.strip()
    if _IDENTITY_MARKER in cleaned_prompt:
        return cleaned_prompt
    instruction = profile.provider_instruction()
    return f"{cleaned_prompt}\n\n{instruction}" if cleaned_prompt else instruction


def proactive_speech_line(
    kind: str,
    profile: AkihaSpeechIdentityProfile = AKIHA_SPEECH_IDENTITY,
) -> str | None:
    """Return an original Japanese line for a supported proactive event."""
    pet_need_line = _PET_NEED_SPEECH_LINES.get(kind)
    if pet_need_line is not None:
        return pet_need_line
    scenario = _PROACTIVE_SCENARIO_BY_KIND.get(kind)
    return profile.sample_phrase(scenario) if scenario is not None else None


def pet_care_speech_line(action: str, *, level_increased: bool = False) -> str | None:
    """Return a bounded local line for one validated care completion."""
    if level_increased:
        return _PET_LEVEL_SPEECH_LINE
    return _PET_CARE_SPEECH_LINES.get(action)


class AkihaSpeechStyleService:
    """Prepare an idempotent spoken copy without rewriting the chat response."""

    def style(
        self,
        text: str,
        mood: CompanionMood | None = None,
    ) -> StyledSpeech:
        """Remove speech-hostile markup and choose a restrained delivery pace."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Speech styling requires non-empty text.")

        spoken_text = _spoken_copy(text)
        if not spoken_text:
            raise ValueError("Speech styling produced empty text.")
        return StyledSpeech(
            text=spoken_text,
            speaking_rate_multiplier=_rate_multiplier_for(mood),
        )


def _spoken_copy(text: str) -> str:
    spoken = text.strip().replace("\r\n", "\n").replace("\r", "\n")
    spoken = _MARKDOWN_LINK.sub(r"\1", spoken)
    spoken = _HEADING_PREFIX.sub("", spoken)
    spoken = _BULLET_PREFIX.sub("", spoken)
    for marker in ("```", "**", "__", "~~", "`"):
        spoken = spoken.replace(marker, "")
    spoken = _EXCESS_BLANK_LINES.sub("\n\n", spoken)
    return spoken.strip()


def _rate_multiplier_for(mood: CompanionMood | None) -> float:
    return {
        CompanionMood.WAITING: 0.97,
        CompanionMood.RESTING: 0.94,
        CompanionMood.CHECKING_IN: 0.97,
        CompanionMood.SLEEPY: 0.94,
    }.get(mood, 1.0)
