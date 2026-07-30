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
        self.assertTrue(result.voice_capture_stopped)
        self.assertTrue(result.voice_transcription_stopped)
        self.assertTrue(result.voice_synthesis_stopped)
        self.assertTrue(result.voice_playback_stopped)
        self.assertTrue(result.voice_engine_stopped)
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

    def test_shutdown_continues_when_timer_stop_fails(self) -> None:
        timer = _FailingTimer()
        thread = _Thread(finished=True)
        threads = [thread]
        logger = logging.getLogger("test_shutdown_timer_failure")

        with self.assertLogs(logger, level="ERROR") as captured:
            result = shutdown_runtime(
                activity_timer=timer,
                active_chat_threads=threads,
                save_window_position=lambda: None,
                logger=logger,
                thread_wait_ms=25,
            )

        self.assertFalse(result.timer_stopped)
        self.assertTrue(result.position_saved)
        self.assertTrue(thread.cancelled)
        self.assertEqual(threads, [])
        self.assertIn("Failed to stop activity timer", captured.output[0])

    def test_shutdown_reports_thread_cancellation_failure(self) -> None:
        timer = _Timer()
        threads = [_FailingThread()]
        logger = logging.getLogger("test_shutdown_thread_failure")

        with self.assertLogs(logger, level="ERROR") as captured:
            result = shutdown_runtime(
                activity_timer=timer,
                active_chat_threads=threads,
                save_window_position=lambda: None,
                logger=logger,
                thread_wait_ms=25,
            )

        self.assertEqual(result.cancelled_threads, 1)
        self.assertEqual(result.unfinished_threads, 1)
        self.assertEqual(threads, [])
        self.assertIn("Failed to stop chat response thread", captured.output[0])

    def test_shutdown_cancels_active_voice_capture(self) -> None:
        capture = _VoiceCapture()

        result = shutdown_runtime(
            activity_timer=_Timer(),
            active_chat_threads=[],
            save_window_position=lambda: None,
            logger=logging.getLogger("test_shutdown_voice"),
            voice_capture=capture,
        )

        self.assertTrue(capture.cancelled)
        self.assertTrue(result.voice_capture_stopped)

    def test_shutdown_reports_voice_capture_failure(self) -> None:
        logger = logging.getLogger("test_shutdown_voice_failure")

        with self.assertLogs(logger, level="ERROR") as captured:
            result = shutdown_runtime(
                activity_timer=_Timer(),
                active_chat_threads=[],
                save_window_position=lambda: None,
                logger=logger,
                voice_capture=_FailingVoiceCapture(),
            )

        self.assertFalse(result.voice_capture_stopped)
        self.assertIn("microphone capture", captured.output[0])

    def test_shutdown_cancels_voice_transcription(self) -> None:
        transcription = _VoiceCapture()

        result = shutdown_runtime(
            activity_timer=_Timer(),
            active_chat_threads=[],
            save_window_position=lambda: None,
            logger=logging.getLogger("test_shutdown_transcription"),
            voice_transcription=transcription,
        )

        self.assertTrue(transcription.cancelled)
        self.assertTrue(result.voice_transcription_stopped)

    def test_shutdown_reports_voice_transcription_failure(self) -> None:
        logger = logging.getLogger("test_shutdown_transcription_failure")

        with self.assertLogs(logger, level="ERROR") as captured:
            result = shutdown_runtime(
                activity_timer=_Timer(),
                active_chat_threads=[],
                save_window_position=lambda: None,
                logger=logger,
                voice_transcription=_FailingVoiceCapture(),
            )

        self.assertFalse(result.voice_transcription_stopped)
        self.assertIn("voice transcription", captured.output[0])

    def test_shutdown_cancels_voice_synthesis(self) -> None:
        synthesis = _VoiceCapture()

        result = shutdown_runtime(
            activity_timer=_Timer(),
            active_chat_threads=[],
            save_window_position=lambda: None,
            logger=logging.getLogger("test_shutdown_synthesis"),
            voice_synthesis=synthesis,
        )

        self.assertTrue(synthesis.cancelled)
        self.assertTrue(result.voice_synthesis_stopped)

    def test_shutdown_reports_voice_synthesis_failure(self) -> None:
        logger = logging.getLogger("test_shutdown_synthesis_failure")

        with self.assertLogs(logger, level="ERROR") as captured:
            result = shutdown_runtime(
                activity_timer=_Timer(),
                active_chat_threads=[],
                save_window_position=lambda: None,
                logger=logger,
                voice_synthesis=_FailingVoiceCapture(),
            )

        self.assertFalse(result.voice_synthesis_stopped)
        self.assertIn("voice synthesis", captured.output[0])

    def test_shutdown_cancels_voice_playback(self) -> None:
        playback = _VoiceCapture()

        result = shutdown_runtime(
            activity_timer=_Timer(),
            active_chat_threads=[],
            save_window_position=lambda: None,
            logger=logging.getLogger("test_shutdown_playback"),
            voice_playback=playback,
        )

        self.assertTrue(playback.cancelled)
        self.assertTrue(result.voice_playback_stopped)

    def test_shutdown_reports_voice_playback_failure(self) -> None:
        logger = logging.getLogger("test_shutdown_playback_failure")

        with self.assertLogs(logger, level="ERROR") as captured:
            result = shutdown_runtime(
                activity_timer=_Timer(),
                active_chat_threads=[],
                save_window_position=lambda: None,
                logger=logger,
                voice_playback=_FailingVoiceCapture(),
            )

        self.assertFalse(result.voice_playback_stopped)
        self.assertIn("voice playback", captured.output[0])

    def test_shutdown_applies_managed_voice_engine_exit_policy(self) -> None:
        engine = _VoiceEngine()

        result = shutdown_runtime(
            activity_timer=_Timer(),
            active_chat_threads=[],
            save_window_position=lambda: None,
            logger=logging.getLogger("test_shutdown_voice_engine"),
            voice_engine=engine,
        )

        self.assertTrue(engine.shutdown_called)
        self.assertTrue(result.voice_engine_stopped)

    def test_shutdown_reports_managed_voice_engine_failure(self) -> None:
        logger = logging.getLogger("test_shutdown_voice_engine_failure")

        with self.assertLogs(logger, level="ERROR") as captured:
            result = shutdown_runtime(
                activity_timer=_Timer(),
                active_chat_threads=[],
                save_window_position=lambda: None,
                logger=logger,
                voice_engine=_FailingVoiceEngine(),
            )

        self.assertFalse(result.voice_engine_stopped)
        self.assertIn("managed voice engine", captured.output[0])


class _Timer:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _FailingTimer:
    def stop(self) -> None:
        raise RuntimeError("timer failed")


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


class _FailingThread:
    def cancel(self) -> None:
        raise RuntimeError("thread failed")

    def wait(self, time: int = 0) -> bool:
        del time
        return False


class _VoiceCapture:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class _FailingVoiceCapture:
    def cancel(self) -> None:
        raise RuntimeError("capture failed")


class _VoiceEngine:
    def __init__(self) -> None:
        self.shutdown_called = False

    def shutdown(self) -> bool:
        self.shutdown_called = True
        return True


class _FailingVoiceEngine:
    def shutdown(self) -> bool:
        raise RuntimeError("engine failed")


if __name__ == "__main__":
    unittest.main()
