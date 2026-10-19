"""The taskbar, for the HUD: where the tray is, keeping a window above the taskbar, the taskbar's
theme, and whether a full-screen app is in front. Rectangles are in real pixels.

Findings from the spike: `Shell_TrayWnd` is the main taskbar and its `TrayNotifyWnd` child is the
tray (icons and clock). Each other monitor's taskbar is a `Shell_SecondaryTrayWnd` with no tray:
Windows 11 draws just a clock at its right end, which isn't a window, so its room is set aside by
the taskbar's height (CLOCK_SHARE).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32")
_advapi32 = ctypes.WinDLL("advapi32")

_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowW.restype = wintypes.HWND
_user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowExW.restype = wintypes.HWND
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowRect.restype = wintypes.BOOL
_user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
_user32.SetWindowPos.restype = wintypes.BOOL
_shell32.SHQueryUserNotificationState.argtypes = [ctypes.POINTER(ctypes.c_int)]
_shell32.SHQueryUserNotificationState.restype = ctypes.c_long
_advapi32.RegGetValueW.argtypes = [
    wintypes.HKEY,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
    ctypes.POINTER(wintypes.DWORD),
]
_advapi32.RegGetValueW.restype = wintypes.LONG

HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
HKEY_CURRENT_USER = 0x80000001
RRF_RT_REG_DWORD = 0x00000010
THEME_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
QUNS_FULL_SCREEN = {2, 3, 4}  # busy (full-screen app), D3D full screen, presentation mode
# Another monitor's clock, two lines of time and date, starts 1.5 taskbar heights from its right
# edge (measured on Windows 11 at 100%); this leaves a little more
CLOCK_SHARE = 1.8


@dataclass(frozen=True)
class Tray:
    """A taskbar, and where the HUD goes on it: just left of `left`, centred in its height."""

    left: int
    top: int
    height: int
    width: int  # the whole taskbar's, to keep the HUD a modest share of it


def find_taskbars() -> tuple[Tray, ...]:
    """The main taskbar, by its tray, then any other monitors' taskbars, by their clock. None
    while Explorer is restarting."""
    main = _user32.FindWindowW("Shell_TrayWnd", None)
    tray = _user32.FindWindowExW(main, None, "TrayNotifyWnd", None)
    icons = wintypes.RECT()
    if not (tray and _user32.GetWindowRect(tray, icons)):
        return ()
    bars = [(_rect(main), icons.left)]
    other = _user32.FindWindowExW(None, None, "Shell_SecondaryTrayWnd", None)
    while other:
        bar = _rect(other)
        bars.append((bar, bar.right - round((bar.bottom - bar.top) * CLOCK_SHARE)))
        other = _user32.FindWindowExW(None, other, "Shell_SecondaryTrayWnd", None)
    return tuple(
        Tray(left, bar.top, bar.bottom - bar.top, bar.right - bar.left)
        for bar, left in bars
        if bar.bottom > bar.top  # empty: it closed as it was found
    )


def _rect(window: int) -> wintypes.RECT:
    rect = wintypes.RECT()
    _user32.GetWindowRect(window, ctypes.byref(rect))
    return rect


def lift(window_id: int) -> None:
    """Back above the taskbar, which covers it after the taskbar is clicked. Never takes focus."""
    flags = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
    _user32.SetWindowPos(window_id, HWND_TOPMOST, 0, 0, 0, 0, flags)


def full_screen_app() -> bool:
    """A video, a game or a presentation is in front, so the HUD should get out of the way."""
    state = ctypes.c_int()
    _shell32.SHQueryUserNotificationState(ctypes.byref(state))
    return state.value in QUNS_FULL_SCREEN


def light_taskbar() -> bool:
    """The taskbar's own theme setting. Read with RegGetValueW, which returns an error code
    rather than raising, so a missing value just means the default: dark."""
    value, size = wintypes.DWORD(0), wintypes.DWORD(4)
    found = _advapi32.RegGetValueW(
        HKEY_CURRENT_USER,
        THEME_KEY,
        "SystemUsesLightTheme",
        RRF_RT_REG_DWORD,
        None,
        ctypes.byref(value),
        ctypes.byref(size),
    )
    return found == 0 and value.value == 1
