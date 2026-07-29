"""Tests for application shutdown cleanup."""

from __future__ import annotations

import logging
import unittest

from project_akiha.app.shutdown import shutdown_runtime


class ShutdownRuntimeTest(unittest.TestCase):
    """Verify shutdown cleanup stops long-running resources."""

    def test_shutdown_stops_timer_saves_position_and_cancels_threads(self) -> None:
        timer = _Timer()
        threads = [_Thread(finished=True), _Thread(finished=True)]
        saved_positions = 0

        def save_position() -> None:
            nonlocal saved_positions
            saved_positions += 1

        result = shutdown_runtime(
            activity_timer=timer,
            active_chat_threads=threads,
            save_window_position=save_position,
            logger=logging.getLogger("test_shutdown"),
            thread_wait_ms=25,
        )

        self.assertTrue(timer.stopped)
        self.assertEqual(saved_positions, 1)
        self.assertEqual(result.cancelled_threads, 2)
        self.assertEqual(result.unfinished_threads, 0)
        self.assertTrue(result.position_saved)
        self.assertTrue(result.timer_stopped)
        self.assertEqual(threads, [])

    def test_shutdown_reports_unfinished_threads(self) -> None:
        timer = _Timer()
        threads = [_Thread(finished=False)]
        logger = logging.getLogger("test_shutdown_unfinished")

        with self.assertLogs(logger, level="WARNING") as captured:
            result = shutdown_runtime(
                activity_timer=timer,
                active_chat_threads=threads,
                save_window_position=lambda: None,
                logger=logger,
                thread_wait_ms=25,
            )

        self.assertEqual(result.unfinished_threads, 1)
        self.assertIn("did not stop", captured.output[0])
        self.assertEqual(threads, [])

    def test_shutdown_continues_when_position_save_fails(self) -> None:
        timer = _Timer()
        thread = _Thread(finished=True)
        threads = [thread]
        logger = logging.getLogger("test_shutdown_save_failure")

        def fail_to_save() -> None:
            raise RuntimeError("disk busy")

        with self.assertLogs(logger, level="ERROR") as captured:
            result = shutdown_runtime(
                activity_timer=timer,
                active_chat_threads=threads,
                save_window_position=fail_to_save,
                logger=logger,
                thread_wait_ms=25,
            )

        self.assertFalse(result.position_saved)
        self.assertTrue(thread.cancelled)
        self.assertEqual(threads, [])
        self.assertIn("Failed to save", captured.output[0])


class _Timer:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _Thread:
    def __init__(self, *, finished: bool) -> None:
        self.finished = finished
        self.cancelled = False
        self.wait_time = 0

    def cancel(self) -> None:
        self.cancelled = True

    def wait(self, time: int = 0) -> bool:
        self.wait_time = time
        return self.finished


if __name__ == "__main__":
    unittest.main()
