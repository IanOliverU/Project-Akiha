"""Privacy-safe errors shared by hosted live-session adapters."""

from __future__ import annotations

from enum import StrEnum


class LiveSessionErrorCode(StrEnum):
    """Stable failure categories safe for UI and diagnostics."""

    INVALID_STATE = "invalid_state"
    CANCELLED = "cancelled"
    CONNECTION_FAILED = "connection_failed"
    CONNECTION_CLOSED = "connection_closed"
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    UNSUPPORTED_CONFIGURATION = "unsupported_configuration"
    UNSUPPORTED_AUDIO_FORMAT = "unsupported_audio_format"
    PROTOCOL_ERROR = "protocol_error"


class LiveSessionError(RuntimeError):
    """A bounded provider-neutral live-session failure."""

    def __init__(
        self,
        code: LiveSessionErrorCode,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        cleaned = " ".join(message.split()).strip()
        if not cleaned:
            cleaned = "The live voice session failed."
        if len(cleaned) > 512:
            cleaned = cleaned[:509].rstrip() + "..."
        super().__init__(cleaned)
        self.code = code
        self.retryable = retryable
