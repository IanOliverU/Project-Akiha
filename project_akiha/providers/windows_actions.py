"""Concrete Windows adapters, injected by the application composition root."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def open_directory(path: Path) -> None:
    """Ask Windows Explorer to open a validated directory, without a shell command."""
    startfile = getattr(os, "startfile", None)
    if startfile is None:
        raise OSError("the system directory opener is unavailable")
    startfile(str(path))


def open_file(path: Path) -> None:
    """Ask Windows to open a validated passive file with its default handler."""
    startfile = getattr(os, "startfile", None)
    if startfile is None:
        raise OSError("the system file opener is unavailable")
    startfile(str(path))


def launch_application(path: Path) -> None:
    """Start a catalog-owned GUI executable with no shell or arguments."""
    subprocess.Popen(
        [str(path)],
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def close_application_windows(path: Path) -> int:
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
