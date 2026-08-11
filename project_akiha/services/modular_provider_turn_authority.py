"""Ephemeral turn ownership for modular provider action proposals."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ModularProviderTurn:
    """Opaque application-owned identity for one modular provider turn."""

    session_id: str
    turn_id: str


class ModularProviderTurnAuthority:
    """Own at most one short-lived modular provider turn."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active: ModularProviderTurn | None = None

    def open_turn(self) -> ModularProviderTurn:
        """Replace any prior turn and return a fresh bounded identity."""
        identity = ModularProviderTurn(
            session_id=f"modular-{uuid4().hex}",
            turn_id=f"turn-{uuid4().hex}",
        )
        with self._lock:
            self._active = identity
        return identity

    def accepts_callback(self, session_id: str, turn_id: str) -> bool:
        """Return whether a callback still belongs to the active turn."""
        with self._lock:
            active = self._active
            return bool(
                active is not None
                and active.session_id == session_id
                and active.turn_id == turn_id
            )

    def close_turn(self, identity: ModularProviderTurn | None = None) -> None:
        """Close the active turn, optionally only when identity still matches."""
        with self._lock:
            if identity is None or self._active == identity:
                self._active = None
