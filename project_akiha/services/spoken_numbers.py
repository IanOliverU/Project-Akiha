"""Small, deterministic English-number parsing for spoken controls."""

from __future__ import annotations

_SMALL_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS_NUMBER_WORDS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}


def parse_english_number(value: str) -> int | None:
    """Parse a bounded digit or simple English number from zero to one hundred."""
    normalized = value.strip().casefold()
    if normalized.isdigit():
        return int(normalized)
    words = normalized.replace("-", " ").split()
    if words == ["one", "hundred"]:
        return 100
    if len(words) == 1:
        return _SMALL_NUMBER_WORDS.get(words[0], _TENS_NUMBER_WORDS.get(words[0]))
    if len(words) == 2 and words[0] in _TENS_NUMBER_WORDS:
        unit = _SMALL_NUMBER_WORDS.get(words[1])
        if unit is not None and 1 <= unit <= 9:
            return _TENS_NUMBER_WORDS[words[0]] + unit
    return None
