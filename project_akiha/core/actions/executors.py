"""Small, capability-specific executors for approved assistant actions."""

from __future__ import annotations

import asyncio
import os
import subprocess
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Protocol

from project_akiha.core.actions.application_catalog import ApplicationCatalog
from project_akiha.core.actions.errors import ActionValidationError
from project_akiha.core.actions.models import (
    ActionExecutionResult,
    ActionFailureCategory,
    ActionStatus,
    DirectorySearchMatch,
    FileSearchMatch,
    ValidatedAction,
)
from project_akiha.core.actions.passive_files import (
    PASSIVE_AUDIO_EXTENSIONS,
    PASSIVE_VIDEO_EXTENSIONS,
    PassiveFilePolicy,
)
from project_akiha.core.actions.registry import (
    CLOSE_APPLICATION_ACTION,
    DIRECTORY_SEARCH_ACTION,
    FILE_SEARCH_ACTION,
    LAUNCH_APPLICATION_ACTION,
    OPEN_DIRECTORY_ACTION,
    OPEN_FILE_ACTION,
)

_WINDOWS_REPARSE_POINT = 0x400
_PASSIVE_MEDIA_EXTENSIONS = PASSIVE_AUDIO_EXTENSIONS | PASSIVE_VIDEO_EXTENSIONS


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
            media_only=bool(action.parameters.get("media_only", False)),
            timeout_seconds=action.definition.timeout_seconds,
            action_max_results=action.definition.max_results,
            cancellation_token=cancellation_token,
        )

    def _search(
        self,
        *,
        root: Path,
        query: str,
        media_only: bool,
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
                            if (
                                media_only
                                and Path(entry.name).suffix.casefold()
                                not in _PASSIVE_MEDIA_EXTENSIONS
                            ):
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


class DirectorySearchExecutor:
    """Search directory names under one approved root without following links."""

    executor_id = "directory_search"
    action_id = DIRECTORY_SEARCH_ACTION

    def __init__(self, *, max_depth: int = 6, max_results: int = 100) -> None:
        if not 0 <= max_depth <= 64:
            raise ValueError("directory search max_depth must be between 0 and 64.")
        if not 1 <= max_results <= 1_000:
            raise ValueError("directory search max_results must be between 1 and 1000.")
        self._max_depth = max_depth
        self._max_results = max_results

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        """Run bounded directory enumeration away from the UI event loop."""
        if action.definition.action_id != self.action_id:
            raise ValueError("directory search executor received the wrong action.")
        return await asyncio.to_thread(
            self._search,
            root=Path(action.normalized_target),
            query=str(action.parameters["query"]),
            match_all=bool(action.parameters.get("match_all", False)),
            timeout_seconds=action.definition.timeout_seconds,
            action_max_results=action.definition.max_results,
            cancellation_token=cancellation_token,
        )

    def _search(
        self,
        *,
        root: Path,
        query: str,
        match_all: bool,
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
        matches: list[DirectorySearchMatch] = []
        pending_directories: list[tuple[Path, int]] = [(root, 0)]
        skipped_entries = 0

        while pending_directories:
            outcome = _interruption_result(
                cancellation_token,
                deadline,
                label="Directory search",
            )
            if outcome is not None:
                return outcome
            directory, depth = pending_directories.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        outcome = _interruption_result(
                            cancellation_token,
                            deadline,
                            label="Directory search",
                        )
                        if outcome is not None:
                            return outcome
                        if _is_link_or_reparse_point(entry):
                            skipped_entries += 1
                            continue
                        try:
                            if not entry.is_dir(follow_symlinks=False):
                                continue
                            child = Path(entry.path)
                            if depth < self._max_depth:
                                pending_directories.append((child, depth + 1))
                            if (
                                not match_all
                                and normalized_query not in entry.name.casefold()
                            ):
                                continue
                            details = entry.stat(follow_symlinks=False)
                        except OSError:
                            skipped_entries += 1
                            continue
                        matches.append(
                            DirectorySearchMatch(
                                name=entry.name,
                                path=str(child),
                                modified_at=datetime.fromtimestamp(
                                    details.st_mtime,
                                    tz=UTC,
                                ).isoformat(),
                            )
                        )
                        if len(matches) >= limit:
                            return _directory_success_result(
                                matches,
                                skipped_entries,
                                limited=True,
                            )
            except OSError:
                skipped_entries += 1

        return _directory_success_result(
            matches,
            skipped_entries,
            limited=False,
        )


class OpenDirectoryExecutor:
    """Open one approved directory through the normal desktop file browser."""

    executor_id = "open_directory"
    action_id = OPEN_DIRECTORY_ACTION

    def __init__(self, opener: Callable[[Path], None] | None = None) -> None:
        self._opener = opener or _open_directory_with_system

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        """Open a validated directory without accepting shell arguments."""
        if action.definition.action_id != self.action_id:
            raise ValueError("directory opener received the wrong action.")
        if cancellation_token.is_cancelled:
            return ActionExecutionResult(
                status=ActionStatus.CANCELLED,
                summary="Directory opening was cancelled.",
            )

        directory = Path(action.normalized_target)
        if _is_path_link_or_reparse_point(directory) or not directory.is_dir():
            return ActionExecutionResult(
                status=ActionStatus.FAILED,
                summary="The approved directory is unavailable.",
                failure_category=ActionFailureCategory.TARGET_UNAVAILABLE,
            )

        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._opener, directory),
                timeout=action.definition.timeout_seconds,
            )
        except TimeoutError:
            return ActionExecutionResult(
                status=ActionStatus.TIMED_OUT,
                summary="Opening the directory reached its time limit.",
            )
        except OSError:
            return ActionExecutionResult(
                status=ActionStatus.FAILED,
                summary="The directory could not be opened.",
                failure_category=ActionFailureCategory.EXECUTION_FAILED,
            )

        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary="The approved directory was opened.",
            metadata={"opened_directory": str(directory)},
        )


class OpenFileExecutor:
    """Open one validated passive file through its normal desktop handler."""

    executor_id = "open_safe_file"
    action_id = OPEN_FILE_ACTION

    def __init__(
        self,
        opener: Callable[[Path], None] | None = None,
        passive_file_policy: PassiveFilePolicy | None = None,
    ) -> None:
        self._opener = opener or _open_file_with_system
        self._passive_file_policy = passive_file_policy or PassiveFilePolicy()

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        """Recheck the file and open it without shell commands or arguments."""
        if action.definition.action_id != self.action_id:
            raise ValueError("file opener received the wrong action.")
        if cancellation_token.is_cancelled:
            return ActionExecutionResult(
                status=ActionStatus.CANCELLED,
                summary="File opening was cancelled.",
            )

        file_path = Path(action.normalized_target)
        try:
            self._passive_file_policy.validate_file(file_path)
        except ActionValidationError as error:
            return ActionExecutionResult(
                status=ActionStatus.FAILED,
                summary="The approved file is unavailable or no longer allowlisted.",
                failure_category=error.category,
            )

        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._opener, file_path),
                timeout=action.definition.timeout_seconds,
            )
        except TimeoutError:
            return ActionExecutionResult(
                status=ActionStatus.TIMED_OUT,
                summary="Opening the file reached its time limit.",
            )
        except OSError:
            return ActionExecutionResult(
                status=ActionStatus.FAILED,
                summary="The file could not be opened.",
                failure_category=ActionFailureCategory.EXECUTION_FAILED,
            )

        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary="The approved file was opened.",
            metadata={"opened_file": str(file_path)},
        )


class AllowlistedApplicationExecutor:
    """Launch only a catalog-resolved application without shell arguments."""

    executor_id = "launch_allowlisted_application"
    action_id = LAUNCH_APPLICATION_ACTION

    def __init__(
        self,
        catalog: ApplicationCatalog | None = None,
        launcher: Callable[[Path], None] | None = None,
    ) -> None:
        self._catalog = catalog or ApplicationCatalog()
        self._launcher = launcher or _launch_application_with_system

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        """Resolve and launch the application-owned executable path."""
        if action.definition.action_id != self.action_id:
            raise ValueError("application launcher received the wrong action.")
        if cancellation_token.is_cancelled:
            return ActionExecutionResult(
                status=ActionStatus.CANCELLED,
                summary="Application launch was cancelled.",
            )

        application_id = action.normalized_target
        application = self._catalog.resolve(application_id)
        if not application.is_available:
            return ActionExecutionResult(
                status=ActionStatus.FAILED,
                summary=f"{application.display_name} was not found on this computer.",
                failure_category=ActionFailureCategory.TARGET_UNAVAILABLE,
                metadata={"application_id": application_id, "available": False},
            )

        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._launcher, application.executable),
                timeout=action.definition.timeout_seconds,
            )
        except TimeoutError:
            return ActionExecutionResult(
                status=ActionStatus.TIMED_OUT,
                summary=f"Starting {application.display_name} reached its time limit.",
            )
        except OSError:
            return ActionExecutionResult(
                status=ActionStatus.FAILED,
                summary=f"{application.display_name} could not be started.",
                failure_category=ActionFailureCategory.EXECUTION_FAILED,
                metadata={"application_id": application_id, "available": True},
            )

        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=f"{application.display_name} was started.",
            metadata={"application_id": application_id, "available": True},
        )


class CloseAllowlistedApplicationExecutor:
    """Gracefully close windows owned by one catalog-resolved application."""

    executor_id = "close_allowlisted_application"
    action_id = CLOSE_APPLICATION_ACTION

    def __init__(
        self,
        catalog: ApplicationCatalog | None = None,
        closer: Callable[[Path], int] | None = None,
    ) -> None:
        self._catalog = catalog or ApplicationCatalog()
        self._closer = closer or _close_application_windows

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        """Request a normal window close without terminating any process."""
        if action.definition.action_id != self.action_id:
            raise ValueError("application closer received the wrong action.")
        if cancellation_token.is_cancelled:
            return ActionExecutionResult(
                status=ActionStatus.CANCELLED,
                summary="Application closing was cancelled.",
            )

        application_id = action.normalized_target
        application = self._catalog.resolve(application_id)
        if not application.is_available:
            return ActionExecutionResult(
                status=ActionStatus.FAILED,
                summary=f"{application.display_name} was not found on this computer.",
                failure_category=ActionFailureCategory.TARGET_UNAVAILABLE,
                metadata={"application_id": application_id, "available": False},
            )

        try:
            closed_windows = await asyncio.wait_for(
                asyncio.to_thread(self._closer, application.executable),
                timeout=action.definition.timeout_seconds,
            )
        except TimeoutError:
            return ActionExecutionResult(
                status=ActionStatus.TIMED_OUT,
                summary=f"Closing {application.display_name} reached its time limit.",
            )
        except OSError:
            return ActionExecutionResult(
                status=ActionStatus.FAILED,
                summary=f"{application.display_name} could not be closed safely.",
                failure_category=ActionFailureCategory.EXECUTION_FAILED,
                metadata={"application_id": application_id, "available": True},
            )

        if closed_windows <= 0:
            return ActionExecutionResult(
                status=ActionStatus.FAILED,
                summary=f"{application.display_name} does not have an open window.",
                failure_category=ActionFailureCategory.TARGET_UNAVAILABLE,
                metadata={
                    "application_id": application_id,
                    "available": True,
                    "closed_windows": 0,
                },
            )
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=f"{application.display_name} was asked to close.",
            metadata={
                "application_id": application_id,
                "available": True,
                "closed_windows": closed_windows,
            },
        )


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


def _open_directory_with_system(path: Path) -> None:
    """Ask Windows Explorer to open a validated directory, without a shell command."""
    startfile = getattr(os, "startfile", None)
    if startfile is None:
        raise OSError("the system directory opener is unavailable")
    startfile(str(path))


def _open_file_with_system(path: Path) -> None:
    """Ask Windows to open a validated passive file with its default handler."""
    startfile = getattr(os, "startfile", None)
    if startfile is None:
        raise OSError("the system file opener is unavailable")
    startfile(str(path))


def _launch_application_with_system(path: Path) -> None:
    """Start a catalog-owned GUI executable with no shell or arguments."""
    subprocess.Popen(
        [str(path)],
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def _close_application_windows(path: Path) -> int:
    """Post WM_CLOSE only to windows owned by the exact catalog executable."""
    if os.name != "nt":
        raise OSError("graceful application closing is available only on Windows")

    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    wm_close = 0x0010
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    )
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    )
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.PostMessageW.argtypes = (
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )
    user32.PostMessageW.restype = wintypes.BOOL

    target = os.path.normcase(os.path.abspath(str(path)))
    closed_windows = 0
    enum_callback = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HWND,
        wintypes.LPARAM,
    )

    @enum_callback
    def request_close(window: int, _: int) -> bool:
        nonlocal closed_windows
        try:
            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
            if not process_id.value:
                return True
            process = kernel32.OpenProcess(
                process_query_limited_information,
                False,
                process_id.value,
            )
            if not process:
                return True
            try:
                capacity = wintypes.DWORD(32768)
                executable = ctypes.create_unicode_buffer(capacity.value)
                if not kernel32.QueryFullProcessImageNameW(
                    process,
                    0,
                    executable,
                    ctypes.byref(capacity),
                ):
                    return True
                candidate = os.path.normcase(os.path.abspath(executable.value))
                if candidate == target and user32.PostMessageW(
                    window,
                    wm_close,
                    0,
                    0,
                ):
                    closed_windows += 1
            finally:
                kernel32.CloseHandle(process)
        except Exception:
            return True
        return True

    user32.EnumWindows.argtypes = (enum_callback, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    ctypes.set_last_error(0)
    enumeration_succeeded = user32.EnumWindows(request_close, 0)
    if not enumeration_succeeded and ctypes.get_last_error():
        raise OSError("Windows could not enumerate application windows")
    return closed_windows


def _interruption_result(
    cancellation_token: ActionCancellationToken,
    deadline: float,
    *,
    label: str = "File search",
) -> ActionExecutionResult | None:
    if cancellation_token.is_cancelled:
        return ActionExecutionResult(
            status=ActionStatus.CANCELLED,
            summary=f"{label} was cancelled.",
        )
    if monotonic() >= deadline:
        return ActionExecutionResult(
            status=ActionStatus.TIMED_OUT,
            summary=f"{label} reached its time limit.",
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


def _directory_success_result(
    matches: list[DirectorySearchMatch],
    skipped_entries: int,
    *,
    limited: bool,
) -> ActionExecutionResult:
    if matches:
        noun = "directory" if len(matches) == 1 else "directories"
        summary = f"Found {len(matches)} matching {noun}."
    else:
        summary = "No matching directories were found."
    return ActionExecutionResult(
        status=ActionStatus.SUCCESS,
        summary=summary,
        metadata={
            "matches": tuple(matches),
            "limited": limited,
            "skipped_entries": skipped_entries,
        },
    )
