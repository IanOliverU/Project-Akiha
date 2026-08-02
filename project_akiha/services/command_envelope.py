"""Conservative extraction of explicit commands from conversational wrappers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_MAX_ENVELOPE_LENGTH = 2_000

_ACTION_VERB = (
    r"(?:open|launch|start|close|quit|exit|play|pause|resume|continue|search|"
    r"find|show|take|turn|switch|set|raise|lower|increase|decrease|mute|seek|"
    r"skip|restart|listen|look|go)"
)
_ACTION_GERUND = (
    r"(?:opening|launching|starting|closing|quitting|exiting|playing|pausing|"
    r"resuming|continuing|searching|finding|showing|taking|turning|switching|"
    r"setting|muting|seeking|skipping|restarting|listening|looking|going)"
)
_NEGATED_COMMAND_PATTERNS = (
    re.compile(
        rf"^(?:please\s*[,;:]?\s*)*(?:do\s+not|don(?:'|\u2019)t|never)\s+"
        rf"(?:you\s+)?(?:please\s+)?{_ACTION_VERB}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^(?:please\s*[,;:]?\s*)*(?:can|could|would|will)\s+you\s+"
        rf"(?:please\s+)?not\s+{_ACTION_VERB}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^(?:please\s*[,;:]?\s*)*(?:would|do)\s+you\s+mind\s+not\s+"
        rf"{_ACTION_GERUND}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^i\s+(?:do\s+not|don(?:'|\u2019)t)\s+(?:want|need)\s+you\s+to\s+"
        rf"{_ACTION_VERB}\b",
        re.IGNORECASE,
    ),
)
_METALINGUISTIC_COMMAND_PATTERNS = (
    re.compile(
        r"^(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
        r"(?:tell|show|explain|teach)\s+(?:me\s+)?"
        r"(?:how|why|whether|what|when)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:do\s+you\s+know\s+)?(?:how|why|what|when|where)\s+"
        r"(?:do|does|did|can|could|would|should|will|is|was)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^(?:why\s+)?did\s+you\s+(?:just\s+)?{_ACTION_VERB}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^(?:are|were)\s+you\s+(?:able|allowed|permitted)\s+to\s+"
        rf"{_ACTION_VERB}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:what\s+would\s+happen\s+if|if\s+(?:i|we|someone)\s+"
        r"(?:asked|told|said|were\s+to)|suppose|supposing|assuming|imagine)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^(?:the\s+)?(?:phrase|command|words?|sentence)\s+"
        rf"[\"'\u201c\u2018]?{_ACTION_VERB}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^[\"'\u201c\u2018]{_ACTION_VERB}\b.+[\"'\u201d\u2019]\s+"
        r"(?:is|was|means|would|can)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^(?:i|you)\s+(?:said|say|asked|mentioned|wrote)\s+"
        rf"[\"'\u201c\u2018]?{_ACTION_VERB}\b",
        re.IGNORECASE,
    ),
    re.compile(r"^(?:repeat\s+after\s+me|quote)\b", re.IGNORECASE),
)

_DIRECT_PREFIX_PATTERNS = (
    re.compile(r"^please\s*[,;:]?\s*", re.IGNORECASE),
    re.compile(
        r"^(?:can|could|would|will)\s+you\s+be\s+able\s+to\s+",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:can|could|would|will)\s+you(?:\s+(?:please|kindly))?\s+",
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
    re.compile(r"^do\s+me\s+a\s+favor\s+and\s+", re.IGNORECASE),
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
    r"when\s+you\s+(?:can|have\s+a\s+moment)|right\s+now)"
    r"(?:\s*[,;]?\s*)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DeterministicCommandEnvelope:
    """One bounded command candidate derived without interpreting its target."""

    command_text: str
    transformed: bool


class CommandEnvelopeRejection(StrEnum):
    """Privacy-safe reason that text cannot become a command candidate."""

    NEGATED = "negated"
    METALINGUISTIC = "metalinguistic"


@dataclass(frozen=True, slots=True)
class CommandEnvelopeAnalysis:
    """Accepted command envelope or an explicit non-execution decision."""

    envelope: DeterministicCommandEnvelope | None
    rejection: CommandEnvelopeRejection | None = None


class DeterministicCommandEnvelopeParser:
    """Remove only anchored, harmless wrappers around an explicit command."""

    def parse(self, text: str) -> DeterministicCommandEnvelope | None:
        """Return one command candidate, or ``None`` for unusable input."""
        return self.analyze(text).envelope

    def analyze(self, text: str) -> CommandEnvelopeAnalysis:
        """Classify guards, then derive at most one safe command candidate."""
        original = text.strip()
        if not original or len(original) > _MAX_ENVELOPE_LENGTH:
            return CommandEnvelopeAnalysis(envelope=None)

        rejection = self._classify_rejection(original)
        if rejection is not None:
            return CommandEnvelopeAnalysis(envelope=None, rejection=rejection)

        bare_command = _TRAILING_PUNCTUATION_PATTERN.sub("", original).rstrip()
        command = self._strip_prefixes(bare_command)
        command = self._strip_courtesy_suffixes(command)
        command = _TRAILING_PUNCTUATION_PATTERN.sub("", command).strip()
        if not command:
            return CommandEnvelopeAnalysis(envelope=None)
        if command == bare_command:
            return CommandEnvelopeAnalysis(
                envelope=DeterministicCommandEnvelope(
                    command_text=original,
                    transformed=False,
                )
            )
        return CommandEnvelopeAnalysis(
            envelope=DeterministicCommandEnvelope(
                command_text=command,
                transformed=True,
            )
        )

    @staticmethod
    def _classify_rejection(text: str) -> CommandEnvelopeRejection | None:
        if any(pattern.search(text) for pattern in _NEGATED_COMMAND_PATTERNS):
            return CommandEnvelopeRejection.NEGATED
        if any(pattern.search(text) for pattern in _METALINGUISTIC_COMMAND_PATTERNS):
            return CommandEnvelopeRejection.METALINGUISTIC
        return None

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
