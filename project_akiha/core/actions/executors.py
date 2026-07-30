"""Small, capability-specific executors for approved assistant actions."""

from __future__ import annotations

import asyncio
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Protocol

from project_akiha.core.actions.models import (
    ActionExecutionResult,
    ActionFailureCategory,
    ActionStatus,
    FileSearchMatch,
    ValidatedAction,
)
from project_akiha.core.actions.registry import FILE_SEARCH_ACTION

_WINDOWS_REPARSE_POINT = 0x400


class ActionCancellationToken:
    """Thread-safe cancellation signal for one bounded assistant action."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """Request cooperative cancellation from the executor."""
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        return self._event.is_set()


class AssistantActionExecutor(Protocol):
    """One exact, application-owned action executor."""

    executor_id: str
    action_id: str

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        """Perform one already-validated and authorized action."""


class FileSearchExecutor:
    """Search regular filenames under one approved root without reading contents."""

    executor_id = "file_search"
    action_id = FILE_SEARCH_ACTION

    def __init__(self, *, max_depth: int = 6, max_results: int = 100) -> None:
        if not 0 <= max_depth <= 64:
            raise ValueError("file search max_depth must be between 0 and 64.")
        if not 1 <= max_results <= 1_000:
            raise ValueError("file search max_results must be between 1 and 1000.")
        self._max_depth = max_depth
        self._max_results = max_results

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        """Run bounded filesystem enumeration away from the UI event loop."""
        if action.definition.action_id != self.action_id:
            raise ValueError("file search executor received the wrong action.")
        return await asyncio.to_thread(
            self._search,
            root=Path(action.normalized_target),
            query=str(action.parameters["query"]),
            timeout_seconds=action.definition.timeout_seconds,
            action_max_results=action.definition.max_results,
            cancellation_token=cancellation_token,
        )

    def _search(
        self,
        *,
        root: Path,
        query: str,
        timeout_seconds: int,
        action_max_results: int | None,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        if _is_path_link_or_reparse_point(root) or not root.is_dir():
            return ActionExecutionResult(
                status=ActionStatus.FAILED,
                summary="The approved directory is unavailable.",
                failure_category=ActionFailureCategory.TARGET_UNAVAILABLE,
            )

        limit = min(
            self._max_results,
            action_max_results if action_max_results is not None else self._max_results,
        )
        deadline = monotonic() + timeout_seconds
        normalized_query = query.casefold()
        matches: list[FileSearchMatch] = []
        pending_directories: list[tuple[Path, int]] = [(root, 0)]
        skipped_entries = 0

        while pending_directories:
            outcome = _interruption_result(cancellation_token, deadline)
            if outcome is not None:
                return outcome

            directory, depth = pending_directories.pop()
            if _is_path_link_or_reparse_point(directory):
                skipped_entries += 1
                continue
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        outcome = _interruption_result(cancellation_token, deadline)
                        if outcome is not None:
                            return outcome
                        if _is_link_or_reparse_point(entry):
                            skipped_entries += 1
                            continue

                        try:
                            if entry.is_dir(follow_symlinks=False):
                                if depth < self._max_depth:
                                    pending_directories.append(
                                        (Path(entry.path), depth + 1)
                                    )
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            if normalized_query not in entry.name.casefold():
                                continue
                            details = entry.stat(follow_symlinks=False)
                        except OSError:
                            skipped_entries += 1
                            continue

                        matches.append(
                            FileSearchMatch(
                                name=entry.name,
                                path=str(Path(entry.path)),
                                size_bytes=details.st_size,
                                modified_at=datetime.fromtimestamp(
                                    details.st_mtime,
                                    tz=UTC,
                                ).isoformat(),
                            )
                        )
                        if len(matches) >= limit:
                            return _success_result(
                                matches, skipped_entries, limited=True
                            )
            except OSError:
                skipped_entries += 1
                continue

        return _success_result(matches, skipped_entries, limited=False)


def _is_link_or_reparse_point(entry: os.DirEntry[str]) -> bool:
    try:
        details = entry.stat(follow_symlinks=False)
    except OSError:
        return True
    attributes = getattr(details, "st_file_attributes", 0)
    return entry.is_symlink() or bool(attributes & _WINDOWS_REPARSE_POINT)


def _is_path_link_or_reparse_point(path: Path) -> bool:
    try:
        details = path.lstat()
    except OSError:
        return True
    attributes = getattr(details, "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & _WINDOWS_REPARSE_POINT)


def _interruption_result(
    cancellation_token: ActionCancellationToken,
    deadline: float,
) -> ActionExecutionResult | None:
    if cancellation_token.is_cancelled:
        return ActionExecutionResult(
            status=ActionStatus.CANCELLED,
            summary="File search was cancelled.",
        )
    if monotonic() >= deadline:
        return ActionExecutionResult(
            status=ActionStatus.TIMED_OUT,
            summary="File search reached its time limit.",
        )
    return None


def _success_result(
    matches: list[FileSearchMatch],
    skipped_entries: int,
    *,
    limited: bool,
) -> ActionExecutionResult:
    if matches:
        summary = f"Found {len(matches)} matching file(s)."
    else:
        summary = "No matching files were found."
    return ActionExecutionResult(
        status=ActionStatus.SUCCESS,
        summary=summary,
        metadata={
            "matches": tuple(matches),
            "limited": limited,
            "skipped_entries": skipped_entries,
        },
    )
