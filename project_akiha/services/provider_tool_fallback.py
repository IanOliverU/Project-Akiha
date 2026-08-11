"""Bounded ownership for one constrained provider fallback per intent turn."""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import uuid4

_TURN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,127}$")


class ProviderToolFallbackState(StrEnum):
    """Privacy-safe lifecycle for one provider fallback turn."""

    READY = "ready"
    JSON_CLAIMED = "json_claimed"
    JSON_CONSUMED = "json_consumed"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class ProviderToolFallbackToken:
    """Opaque identity required to start or close one fallback turn."""

    turn_id: str
    nonce: str

    def __post_init__(self) -> None:
        if not _TURN_ID_PATTERN.fullmatch(self.turn_id):
            raise ValueError("fallback turn ID contains invalid characters.")
        if not _TURN_ID_PATTERN.fullmatch(self.nonce):
            raise ValueError("fallback nonce contains invalid characters.")


@dataclass(frozen=True, slots=True)
class _FallbackRecord:
    token: ProviderToolFallbackToken
    state: ProviderToolFallbackState


class ProviderToolFallbackGate:
    """Allow at most one constrained JSON handoff for each opened turn."""

    def __init__(self, *, max_turns: int = 128) -> None:
        if max_turns <= 0:
            raise ValueError("fallback turn bound must be positive.")
        self._max_turns = max_turns
        self._lock = threading.RLock()
        self._records: OrderedDict[str, _FallbackRecord] = OrderedDict()

    def open_turn(self, turn_id: str) -> ProviderToolFallbackToken:
        """Open a fresh owned turn without granting a JSON request yet."""
        token = ProviderToolFallbackToken(
            turn_id=turn_id,
            nonce=f"fallback-{uuid4().hex}",
        )
        with self._lock:
            self._records[turn_id] = _FallbackRecord(
                token=token,
                state=ProviderToolFallbackState.READY,
            )
            self._records.move_to_end(turn_id)
            while len(self._records) > self._max_turns:
                self._records.popitem(last=False)
        return token

    def claim_json(self, token: ProviderToolFallbackToken) -> bool:
        """Claim exactly one constrained JSON request for an active token."""
        with self._lock:
            record = self._records.get(token.turn_id)
            if (
                record is None
                or record.token != token
                or record.state is not ProviderToolFallbackState.READY
            ):
                return False
            self._records[token.turn_id] = replace(
                record,
                state=ProviderToolFallbackState.JSON_CLAIMED,
            )
            self._records.move_to_end(token.turn_id)
            return True

    def state(
        self,
        token: ProviderToolFallbackToken,
    ) -> ProviderToolFallbackState | None:
        """Return sanitized state only when the token still owns the turn."""
        with self._lock:
            record = self._records.get(token.turn_id)
            if record is None or record.token != token:
                return None
            return record.state

    def accepts_json(self, token: ProviderToolFallbackToken) -> bool:
        """Return whether JSON output still owns the active fallback turn."""
        return self.state(token) is ProviderToolFallbackState.JSON_CLAIMED

    def consume_json(self, token: ProviderToolFallbackToken) -> bool:
        """Consume exactly one JSON result or failure callback."""
        with self._lock:
            record = self._records.get(token.turn_id)
            if (
                record is None
                or record.token != token
                or record.state is not ProviderToolFallbackState.JSON_CLAIMED
            ):
                return False
            self._records[token.turn_id] = replace(
                record,
                state=ProviderToolFallbackState.JSON_CONSUMED,
            )
            self._records.move_to_end(token.turn_id)
            return True

    def close_turn(self, token: ProviderToolFallbackToken) -> None:
        """Invalidate a token without disturbing a replacement turn."""
        with self._lock:
            record = self._records.get(token.turn_id)
            if record is None or record.token != token:
                return
            self._records[token.turn_id] = replace(
                record,
                state=ProviderToolFallbackState.CLOSED,
            )
            self._records.move_to_end(token.turn_id)

    def clear(self) -> None:
        """Invalidate every token during provider changes or shutdown."""
        with self._lock:
            self._records.clear()
