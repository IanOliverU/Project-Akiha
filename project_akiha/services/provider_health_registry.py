"""Thread-safe, privacy-safe health snapshots for optional runtime providers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock

_PROVIDERS = {
    "ai_provider",
    "discord",
    "gemini_live",
    "gmail",
    "gpt_sovits",
    "ollama",
    "voice_input",
}
_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ProviderHealthState(StrEnum):
    """Common optional-provider health vocabulary."""

    STARTING = "starting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    AUTHENTICATION_FAILURE = "authentication_failure"
    PERMISSION_FAILURE = "permission_failure"
    NETWORK_FAILURE = "network_failure"
    RATE_LIMITED = "rate_limited"
    INVALID_CONFIGURATION = "invalid_configuration"
    RECOVERING = "recovering"


@dataclass(frozen=True, slots=True)
class ProviderHealthRecord:
    """One bounded diagnostic record with no provider payload or secret."""

    provider: str
    state: ProviderHealthState
    reason_code: str
    checked_at: datetime
    startup_duration_ms: int | None = None


class ProviderHealthRegistry:
    """Collect optional-provider health without blocking core readiness."""

    def __init__(self) -> None:
        self._records: dict[str, ProviderHealthRecord] = {}
        self._lock = Lock()

    def update(
        self,
        provider: str,
        state: ProviderHealthState | str,
        reason_code: str,
        *,
        checked_at: datetime | None = None,
        startup_duration_ms: int | None = None,
    ) -> ProviderHealthRecord:
        if provider not in _PROVIDERS:
            raise ValueError("Unknown optional provider.")
        parsed_state = ProviderHealthState(state)
        if _CODE.fullmatch(reason_code) is None:
            raise ValueError("Provider health reason must be a privacy-safe code.")
        if startup_duration_ms is not None and not 0 <= startup_duration_ms <= 600_000:
            raise ValueError("Provider startup duration is out of range.")
        timestamp = checked_at or datetime.now(tz=UTC)
        if timestamp.tzinfo is None:
            raise ValueError("Provider health timestamp must be timezone-aware.")
        record = ProviderHealthRecord(
            provider=provider,
            state=parsed_state,
            reason_code=reason_code,
            checked_at=timestamp,
            startup_duration_ms=startup_duration_ms,
        )
        with self._lock:
            self._records[provider] = record
        return record

    def snapshot(self) -> tuple[ProviderHealthRecord, ...]:
        """Return a stable provider-name ordered snapshot."""
        with self._lock:
            return tuple(self._records[key] for key in sorted(self._records))


def render_provider_health_summary(
    records: tuple[ProviderHealthRecord, ...],
) -> str:
    """Render a compact Settings summary using only bounded codes."""
    if not records:
        return "Optional provider health has not been checked yet."
    parts = []
    for record in records:
        duration = (
            f", {record.startup_duration_ms} ms"
            if record.startup_duration_ms is not None
            else ""
        )
        parts.append(
            f"{record.provider.replace('_', ' ').title()}: "
            f"{record.state.value.replace('_', ' ')} ({record.reason_code}{duration})"
        )
    return "\n".join(parts)


def provider_health_state_from_code(code: str) -> ProviderHealthState:
    """Map existing provider status codes into the shared health vocabulary."""
    normalized = code.strip().lower()
    if normalized in {"available", "connected", "cursor_rebased", "running", "healthy"}:
        return ProviderHealthState.HEALTHY
    if normalized in {"starting", "connecting"}:
        return ProviderHealthState.STARTING
    if normalized in {"recovering", "reconnecting"}:
        return ProviderHealthState.RECOVERING
    if normalized in {
        "authentication_failure",
        "permission_failure",
        "network_failure",
        "rate_limited",
        "invalid_configuration",
    }:
        return ProviderHealthState(normalized)
    if normalized == "disabled":
        return ProviderHealthState.DISABLED
    if normalized == "degraded":
        return ProviderHealthState.DEGRADED
    return ProviderHealthState.UNAVAILABLE
