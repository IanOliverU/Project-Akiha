"""Tests for modular provider turn ownership."""

from __future__ import annotations

import unittest

from project_akiha.services.modular_provider_turn_authority import (
    ModularProviderTurnAuthority,
)


class ModularProviderTurnAuthorityTest(unittest.TestCase):
    """Verify replacement, stale rejection, and bounded cleanup."""

    def test_open_turn_accepts_only_its_current_identity(self) -> None:
        authority = ModularProviderTurnAuthority()

        turn = authority.open_turn()

        self.assertTrue(authority.accepts_callback(turn.session_id, turn.turn_id))
        self.assertFalse(authority.accepts_callback(turn.session_id, "turn-stale"))

    def test_new_turn_invalidates_previous_turn(self) -> None:
        authority = ModularProviderTurnAuthority()
        previous = authority.open_turn()

        current = authority.open_turn()

        self.assertFalse(
            authority.accepts_callback(previous.session_id, previous.turn_id)
        )
        self.assertTrue(authority.accepts_callback(current.session_id, current.turn_id))

    def test_close_with_stale_identity_does_not_close_replacement(self) -> None:
        authority = ModularProviderTurnAuthority()
        previous = authority.open_turn()
        current = authority.open_turn()

        authority.close_turn(previous)

        self.assertTrue(authority.accepts_callback(current.session_id, current.turn_id))
        authority.close_turn(current)
        self.assertFalse(
            authority.accepts_callback(current.session_id, current.turn_id)
        )


if __name__ == "__main__":
    unittest.main()
