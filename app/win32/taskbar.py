"""The taskbars, for the HUD: which are showing and where, keeping a window above them, and the
taskbar's theme. Rectangles are in real pixels.

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
_user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_user32.MonitorFromWindow.restype = wintypes.HMONITOR
_user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
_user32.GetMonitorInfoW.restype = wintypes.BOOL
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = ctypes.c_long
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
MONITOR_DEFAULTTONEAREST = 2
GWL_EXSTYLE, WS_EX_TOPMOST = -20, 0x8
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
    main: bool  # the one with the tray, where the HUD has the most room
    showing: bool  # on screen and on top: see _showing


def find_taskbars() -> tuple[Tray, ...]:
    """Every taskbar along the bottom or top of a monitor, the main one first, then the others
    from left to right: one hiding doesn't move the others, so each keeps its HUD. None while
    Explorer is restarting."""
    main = _user32.FindWindowW("Shell_TrayWnd", None)
    tray = _user32.FindWindowExW(main, None, "TrayNotifyWnd", None)
    icons = wintypes.RECT()
    if not (tray and _user32.GetWindowRect(tray, icons)):
        return ()
    found = [(main, _rect(main), icons.left)]
    other = _user32.FindWindowExW(None, None, "Shell_SecondaryTrayWnd", None)
    while other:
        bar = _rect(other)
        found.append((other, bar, bar.right - round((bar.bottom - bar.top) * CLOCK_SHARE)))
        other = _user32.FindWindowExW(None, other, "Shell_SecondaryTrayWnd", None)
    trays = [
        Tray(
            left=left,
            top=bar.top,
            height=bar.bottom - bar.top,
            width=bar.right - bar.left,
            main=window == main,
            showing=_showing(window, bar),
        )
        for window, bar, left in found
        if bar.right - bar.left > bar.bottom - bar.top  # not up the side, nor empty
    ]
    return tuple(sorted(trays, key=lambda each: (not each.main, each.left, each.top)))


def _showing(window: int, bar: wintypes.RECT) -> bool:
    """All of it on its monitor (not slid away: auto-hide) and on top. Explorer takes a taskbar
    off the top while a full-screen window (a video, a game) covers its monitor, whichever window
    is in front; the HUD goes with it."""
    info = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
    monitor = _user32.MonitorFromWindow(window, MONITOR_DEFAULTTONEAREST)
    _user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    screen = info.rcMonitor
    on_screen = screen.left <= bar.left and bar.right <= screen.right
    on_screen = on_screen and screen.top <= bar.top and bar.bottom <= screen.bottom
    return on_screen and bool(_user32.GetWindowLongW(window, GWL_EXSTYLE) & WS_EX_TOPMOST)


class _MonitorInfo(ctypes.Structure):
    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    )


def _rect(window: int) -> wintypes.RECT:
    rect = wintypes.RECT()
    _user32.GetWindowRect(window, ctypes.byref(rect))
    return rect


def lift(window_id: int) -> None:
    """Back above the taskbar, which covers it after the taskbar is clicked. Never takes focus."""
    flags = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
    _user32.SetWindowPos(window_id, HWND_TOPMOST, 0, 0, 0, 0, flags)


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
