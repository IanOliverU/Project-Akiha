"""Conservative extraction of explicit commands from conversational wrappers."""

from __future__ import annotations

import re
from dataclasses import dataclass

_MAX_ENVELOPE_LENGTH = 2_000

_DIRECT_PREFIX_PATTERNS = (
    re.compile(r"^please\s*[,;:]?\s*", re.IGNORECASE),
    re.compile(
        r"^(?:can|could|would|will)\s+you(?:\s+please)?\s+",
        re.IGNORECASE,
    ),
    re.compile(
        r"^would\s+it\s+be\s+possible\s+for\s+you\s+to\s+",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:i(?:'d|\s+would)\s+like|i\s+(?:want|need))\s+you\s+to\s+",
        re.IGNORECASE,
    ),
    re.compile(r"^just\s+", re.IGNORECASE),
)
_MIND_PREFIX_PATTERN = re.compile(
    r"^(?:would|do)\s+you\s+mind(?:\s+please)?\s+"
    r"(?P<verb>opening|launching|starting|closing|quitting|exiting|playing|"
    r"pausing|resuming|continuing|searching|finding|showing|taking|turning|"
    r"switching|setting|muting|seeking|skipping|restarting|listening|looking)\b",
    re.IGNORECASE,
)
_IMPERATIVE_FORMS = {
    "opening": "open",
    "launching": "launch",
    "starting": "start",
    "closing": "close",
    "quitting": "quit",
    "exiting": "exit",
    "playing": "play",
    "pausing": "pause",
    "resuming": "resume",
    "continuing": "continue",
    "searching": "search",
    "finding": "find",
    "showing": "show",
    "taking": "take",
    "turning": "turn",
    "switching": "switch",
    "setting": "set",
    "muting": "mute",
    "seeking": "seek",
    "skipping": "skip",
    "restarting": "restart",
    "listening": "listen",
    "looking": "look",
}
_TRAILING_PUNCTUATION_PATTERN = re.compile(r"[.!?]+$")
_TRAILING_COURTESY_PATTERN = re.compile(
    r"(?:\s*[,;]?\s*)"
    r"(?:please|for\s+me|if\s+you\s+(?:can|could)|"
    r"when\s+you\s+(?:can|have\s+a\s+moment)|right\s+now)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DeterministicCommandEnvelope:
    """One bounded command candidate derived without interpreting its target."""

    command_text: str
    transformed: bool


class DeterministicCommandEnvelopeParser:
    """Remove only anchored, harmless wrappers around an explicit command."""

    def parse(self, text: str) -> DeterministicCommandEnvelope | None:
        """Return one command candidate, or ``None`` for unusable input."""
        original = text.strip()
        if not original or len(original) > _MAX_ENVELOPE_LENGTH:
            return None

        bare_command = _TRAILING_PUNCTUATION_PATTERN.sub("", original).rstrip()
        command = self._strip_prefixes(bare_command)
        command = self._strip_courtesy_suffixes(command)
        command = _TRAILING_PUNCTUATION_PATTERN.sub("", command).strip()
        if not command:
            return None
        if command == bare_command:
            return DeterministicCommandEnvelope(
                command_text=original,
                transformed=False,
            )
        return DeterministicCommandEnvelope(
            command_text=command,
            transformed=True,
        )

    @staticmethod
    def _strip_prefixes(text: str) -> str:
        command = text
        while command:
            previous = command
            mind_match = _MIND_PREFIX_PATTERN.match(command)
            if mind_match is not None:
                imperative = _IMPERATIVE_FORMS[mind_match.group("verb").casefold()]
                command = f"{imperative}{command[mind_match.end():]}".strip()
            else:
                for pattern in _DIRECT_PREFIX_PATTERNS:
                    command = pattern.sub("", command, count=1).strip()
                    if command != previous:
                        break
            if command == previous:
                break
        return command

    @staticmethod
    def _strip_courtesy_suffixes(text: str) -> str:
        command = text
        while command:
            unwrapped = _TRAILING_COURTESY_PATTERN.sub("", command, count=1).strip()
            if unwrapped == command:
                return command
            command = unwrapped
        return command
