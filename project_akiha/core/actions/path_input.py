"""Recognize private path syntax without creating a decoded execution target."""

from __future__ import annotations

import re
import unicodedata
from pathlib import PureWindowsPath
from urllib.parse import unquote

MAX_CLARIFICATION_INPUT = 4096
MAX_PATH_DECODE_DEPTH = 8


def _embedded_path_material(value: str) -> bool:
    """Fail closed on bounded path/encoding detection; never return decoded data."""
    if len(value) > MAX_CLARIFICATION_INPUT:
        return True
    candidate = value
    for depth in range(MAX_PATH_DECODE_DEPTH + 1):
        candidate = unicodedata.normalize("NFKC", candidate)
        candidate = candidate.translate(str.maketrans({"∕": "/", "⁄": "/"}))
        candidate = "".join(
            c for c in candidate if unicodedata.category(c) not in {"Cc", "Cf"}
        )
        if len(candidate) > MAX_CLARIFICATION_INPUT:
            return True
        if any(c in candidate for c in "/\\") or re.search(
            r"\b(?:file\s*:|[a-z]\s*:)|(?:^|\s)\.{1,2}(?:\s|$)", candidate, re.I
        ):
            return True
        if re.search(r"\b[\w-]+\.[a-z][a-z0-9]{0,7}\b", candidate, re.I):
            return True
        if re.search(r"%(?:2f|5c|3a|2e)", candidate, re.I):
            return True
        # A bare numeric percentage is ordinary prose. Other incomplete/invalid
        # percent escapes are ambiguous encoded material and stay local.
        if re.search(r"%(?![0-9a-f]{2}|(?:\s|$))", candidate, re.I):
            return True
        if not re.search(r"%[0-9a-f]{2}", candidate, re.I):
            return bool(re.search(r"(?<!\d)%(?:\s|$)", candidate))
        if depth == MAX_PATH_DECODE_DEPTH:
            return True
        try:
            candidate = unquote(candidate, errors="strict")
        except UnicodeDecodeError:
            return True
    return True


def looks_like_private_path(value: str, *, embedded: bool = False) -> bool:
    """Detect paths without decoding an execution target or swallowing plain chat."""
    if embedded:
        return _embedded_path_material(value)
    candidate = value
    # Decoding is detection only. Never return this string to a resolver/executor.
    for _ in range(4):
        candidate = unicodedata.normalize("NFKC", candidate).strip().strip("\"'")
        candidate = candidate.translate(str.maketrans({"∕": "/", "⁄": "/"}))
        candidate = "".join(
            c for c in candidate if unicodedata.category(c) not in {"Cc", "Cf"}
        )
        if re.match(r"(?:[a-z]:|file\s*:|[/\\]|\.{1,2}[/\\]|~[/\\])", candidate, re.I):
            return True
        if re.fullmatch(r"[^\s:]+(?:[/\\][^\s:]+)+", candidate):
            return True
        embedded_candidate = re.sub(r"\bhttps?://[^\s\"']+", "", candidate, flags=re.I)
        if embedded and (
            re.search(
                r"(?:^|[\s\"'(=])(?:[a-z]:[/\\]|file\s*:|[/\\]|~[/\\]|\.{1,2}[/\\])",
                embedded_candidate,
                re.I,
            )
            or re.search(
                r"(?<!\w)(?:[\w][\w.-]+[/\\][\w]|[\w][/\\][\w][\w.-]+)",
                embedded_candidate,
            )
        ):
            return True
        decoded = unquote(candidate)
        if decoded == candidate:
            break
        candidate = decoded.strip().strip("\"'")
    return False


def ambiguous_provider_path(value: str) -> bool:
    """Reject unsafe syntax before display-alias normalization or resolution."""
    candidate = value.strip()
    if (
        not candidate
        or unicodedata.normalize("NFKC", candidate) != candidate
        or any(unicodedata.category(c) in {"Cc", "Cf"} for c in value)
        or any(c in candidate for c in '%:<>|?*"∕⁄')
        or candidate.startswith(("/", "\\", "~", "'"))
        or bool(PureWindowsPath(candidate).drive)
        or ("/" in candidate and "\\" in candidate)
    ):
        return True
    parts = re.split(r"[/\\]", candidate)
    return any(
        not part or part in {".", ".."} or part != part.strip() or part.endswith(".")
        for part in parts
    )
