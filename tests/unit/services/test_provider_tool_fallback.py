"""Tests for constrained provider fallback ownership."""

from __future__ import annotations

import unittest

from project_akiha.services.provider_tool_fallback import (
    ProviderToolFallbackGate,
    ProviderToolFallbackState,
)


class ProviderToolFallbackGateTest(unittest.TestCase):
    """Verify one-shot JSON claims, replacement, and cleanup."""

    def test_opened_turn_allows_exactly_one_json_claim(self) -> None:
        gate = ProviderToolFallbackGate()
        token = gate.open_turn("intent-turn-one")

        self.assertEqual(gate.state(token), ProviderToolFallbackState.READY)
        self.assertTrue(gate.claim_json(token))
        self.assertTrue(gate.accepts_json(token))
        self.assertFalse(gate.claim_json(token))
        self.assertTrue(gate.consume_json(token))
        self.assertFalse(gate.consume_json(token))
        self.assertEqual(
            gate.state(token),
            ProviderToolFallbackState.JSON_CONSUMED,
        )

    def test_replacement_token_rejects_late_prior_handoff(self) -> None:
        gate = ProviderToolFallbackGate()
        stale = gate.open_turn("intent-turn-one")

        current = gate.open_turn("intent-turn-one")

        self.assertFalse(gate.claim_json(stale))
        self.assertIsNone(gate.state(stale))
        self.assertTrue(gate.claim_json(current))

    def test_close_and_clear_reject_late_handoffs(self) -> None:
        gate = ProviderToolFallbackGate()
        closed = gate.open_turn("intent-turn-closed")
        cleared = gate.open_turn("intent-turn-cleared")

        gate.close_turn(closed)
        self.assertEqual(gate.state(closed), ProviderToolFallbackState.CLOSED)
        self.assertFalse(gate.claim_json(closed))
        self.assertFalse(gate.accepts_json(closed))
        gate.clear()

        self.assertIsNone(gate.state(cleared))
        self.assertFalse(gate.claim_json(cleared))

    def test_oldest_turn_is_evicted_at_configured_bound(self) -> None:
        gate = ProviderToolFallbackGate(max_turns=2)
        oldest = gate.open_turn("intent-turn-one")
        gate.open_turn("intent-turn-two")

        gate.open_turn("intent-turn-three")

        self.assertIsNone(gate.state(oldest))
        self.assertFalse(gate.claim_json(oldest))


if __name__ == "__main__":
    unittest.main()
