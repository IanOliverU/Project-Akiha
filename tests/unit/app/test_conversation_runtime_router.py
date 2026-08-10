"""Tests for explicit, fail-closed conversation lane routing."""

from __future__ import annotations

import unittest

from project_akiha.app.conversation_runtime_router import (
    ConversationRuntimeLane,
    ConversationRuntimeRouter,
)


class ConversationRuntimeRouterTest(unittest.TestCase):
    def test_local_selection_never_starts_hosted_runtime(self) -> None:
        local = _Runtime(start_result=True)
        hosted = _Runtime(start_result=True)
        router = _router("local_modular", local, hosted)

        self.assertTrue(router.start())

        self.assertEqual(local.start_count, 1)
        self.assertEqual(hosted.start_count, 0)
        self.assertEqual(router.active_lane, ConversationRuntimeLane.LOCAL_MODULAR)

    def test_hosted_selection_never_starts_local_runtime(self) -> None:
        local = _Runtime(start_result=True)
        hosted = _Runtime(start_result=True)
        router = _router("gemini_live", local, hosted)

        self.assertTrue(router.start())

        self.assertEqual(local.start_count, 0)
        self.assertEqual(hosted.start_count, 1)
        self.assertEqual(router.active_lane, ConversationRuntimeLane.GEMINI_LIVE)

    def test_hosted_start_failure_does_not_fall_back_to_local(self) -> None:
        local = _Runtime(start_result=True)
        hosted = _Runtime(start_result=False)
        router = _router("gemini_live", local, hosted)

        self.assertFalse(router.start())

        self.assertEqual(hosted.start_count, 1)
        self.assertEqual(local.start_count, 0)
        self.assertIsNone(router.active_lane)

    def test_async_hosted_stop_only_clears_lane(self) -> None:
        local = _Runtime(start_result=True)
        hosted = _Runtime(start_result=True)
        router = _router("gemini_live", local, hosted)
        router.start()
        hosted.active = False

        router.runtime_stopped(ConversationRuntimeLane.GEMINI_LIVE)

        self.assertIsNone(router.active_lane)
        self.assertEqual(local.start_count, 0)

    def test_end_targets_only_the_runtime_that_started(self) -> None:
        local = _Runtime(start_result=True)
        hosted = _Runtime(start_result=True)
        router = _router("gemini_live", local, hosted)
        router.start()

        self.assertTrue(router.end("provider_changed"))

        self.assertEqual(hosted.end_reasons, ["provider_changed"])
        self.assertEqual(local.end_reasons, [])
        self.assertIsNone(router.active_lane)


class _Runtime:
    def __init__(self, *, start_result: bool) -> None:
        self.start_result = start_result
        self.active = False
        self.start_count = 0
        self.end_reasons: list[str] = []
        self.close_count = 0

    def start(self) -> bool:
        self.start_count += 1
        self.active = self.start_result
        return self.start_result

    def end(self, reason: str = "user") -> bool:
        self.end_reasons.append(reason)
        was_active = self.active
        self.active = False
        return was_active

    def close(self) -> None:
        self.close_count += 1
        self.active = False


def _router(
    selection: str,
    local: _Runtime,
    hosted: _Runtime,
) -> ConversationRuntimeRouter:
    return ConversationRuntimeRouter(
        selection_provider=lambda: selection,
        local_runtime=local,
        hosted_runtime=hosted,
    )


if __name__ == "__main__":
    unittest.main()
