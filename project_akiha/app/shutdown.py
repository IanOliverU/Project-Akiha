"""Application shutdown cleanup helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class StoppableTimer(Protocol):
    """Timer-like object that can be stopped."""

    def stop(self) -> None:
        """Stop the timer."""


class CancellableThread(Protocol):
    """Thread-like chat worker that supports cooperative cancellation."""

    def cancel(self) -> None:
        """Request cancellation."""

    def wait(self, time: int = ...) -> bool:
        """Wait for completion and return whether the thread finished."""


class CancellableVoiceCapture(Protocol):
    """Voice capture resource that can release the microphone."""

    def cancel(self) -> None:
        """Stop capture and discard temporary audio."""


@dataclass(frozen=True, slots=True)
class ShutdownResult:
    """Summary of shutdown cleanup work."""

    position_saved: bool
    cancelled_threads: int
    unfinished_threads: int
    timer_stopped: bool
    voice_capture_stopped: bool


def shutdown_runtime(
    *,
    activity_timer: StoppableTimer,
    active_chat_threads: list[CancellableThread],
    save_window_position: Callable[[], None],
    logger: logging.Logger,
    thread_wait_ms: int = 2000,
    voice_capture: CancellableVoiceCapture | None = None,
) -> ShutdownResult:
    """Stop long-running app resources before Qt exits."""
    timer_stopped = _stop_timer(activity_timer, logger)
    position_saved = _save_position(save_window_position, logger)
    cancelled_threads, unfinished_threads = _cancel_chat_threads(
        active_chat_threads=active_chat_threads,
        logger=logger,
        thread_wait_ms=thread_wait_ms,
    )
    voice_capture_stopped = _cancel_voice_capture(voice_capture, logger)
    return ShutdownResult(
        position_saved=position_saved,
        cancelled_threads=cancelled_threads,
        unfinished_threads=unfinished_threads,
        timer_stopped=timer_stopped,
        voice_capture_stopped=voice_capture_stopped,
    )


def _stop_timer(activity_timer: StoppableTimer, logger: logging.Logger) -> bool:
    try:
        activity_timer.stop()
    except Exception:
        logger.exception("Failed to stop activity timer during shutdown.")
        return False

    return True


def _save_position(
    save_window_position: Callable[[], None],
    logger: logging.Logger,
) -> bool:
    try:
        save_window_position()
    except Exception:
        logger.exception("Failed to save pet window position during shutdown.")
        return False

    return True


def _cancel_chat_threads(
    *,
    active_chat_threads: list[CancellableThread],
    logger: logging.Logger,
    thread_wait_ms: int,
) -> tuple[int, int]:
    cancelled_threads = 0
    unfinished_threads = 0
    for thread in tuple(active_chat_threads):
        cancelled_threads += 1
        try:
            thread.cancel()
            if not thread.wait(thread_wait_ms):
                unfinished_threads += 1
                logger.warning("Chat response thread did not stop during shutdown.")
        except Exception:
            unfinished_threads += 1
            logger.exception("Failed to stop chat response thread during shutdown.")

    active_chat_threads.clear()
    return cancelled_threads, unfinished_threads


def _cancel_voice_capture(
    voice_capture: CancellableVoiceCapture | None,
    logger: logging.Logger,
) -> bool:
    if voice_capture is None:
        return True
    try:
        voice_capture.cancel()
    except Exception:
        logger.exception("Failed to stop microphone capture during shutdown.")
        return False
    return True
