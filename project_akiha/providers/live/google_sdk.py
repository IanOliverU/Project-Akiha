"""Observable loading boundary for the optional Google Gen AI SDK."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_MODULE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


class GoogleGenAISdkImportError(RuntimeError):
    """A privacy-safe Google SDK import failure."""

    def __init__(self, detail: str, *, missing_module: str = "") -> None:
        super().__init__(detail)
        self.missing_module = missing_module


@dataclass(frozen=True, slots=True)
class GoogleGenAISdkProbe:
    """Result of importing the same SDK symbols used by Gemini Live."""

    available: bool
    detail: str
    missing_module: str = ""


def load_google_genai_sdk() -> tuple[Any, Any]:
    """Import and validate the SDK objects required by the live transport."""
    try:
        from google import genai
        from google.genai import types
    except (ImportError, ModuleNotFoundError) as error:
        missing_module = _safe_module_name(getattr(error, "name", ""))
        if missing_module:
            detail = (
                "Gemini Live could not load its packaged SDK dependency "
                f"'{missing_module}'."
            )
        else:
            detail = (
                "Gemini Live could not initialize the packaged google-genai SDK "
                f"({type(error).__name__})."
            )
        raise GoogleGenAISdkImportError(
            detail,
            missing_module=missing_module,
        ) from error

    if not callable(getattr(genai, "Client", None)):
        raise GoogleGenAISdkImportError(
            "Gemini Live loaded google-genai, but its Client API is unavailable."
        )
    if not callable(getattr(types, "FunctionResponse", None)):
        raise GoogleGenAISdkImportError(
            "Gemini Live loaded google-genai, but its type API is incomplete."
        )
    return genai, types


def probe_google_genai_sdk() -> GoogleGenAISdkProbe:
    """Exercise the real import path without opening a network connection."""
    try:
        load_google_genai_sdk()
    except GoogleGenAISdkImportError as error:
        return GoogleGenAISdkProbe(
            available=False,
            detail=str(error),
            missing_module=error.missing_module,
        )
    return GoogleGenAISdkProbe(
        available=True,
        detail="The google-genai SDK loaded successfully.",
    )


def _safe_module_name(value: object) -> str:
    candidate = str(value or "").strip()
    if _MODULE_NAME_PATTERN.fullmatch(candidate):
        return candidate
    return ""
