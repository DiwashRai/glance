"""Ctrl+Space, registered with Windows.

`RegisterHotKey` with no window: Windows posts `WM_HOTKEY` to our thread, and Qt hands it to
the native event filter below. No keyboard hooks, so nothing watches other keys.
"""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QByteArray

HOTKEY_ID = 0x6C61  # any number unique to this app, below 0xC000
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_SPACE = 0x20
WM_HOTKEY = 0x0312
ERROR_HOTKEY_ALREADY_REGISTERED = 1409
HOTKEY_EVENT_TYPE = b"windows_generic_MSG"  # what WM_HOTKEY arrives as (checked with a probe)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.UnregisterHotKey.restype = wintypes.BOOL


class HotkeyTaken(RuntimeError):
    pass


class Hotkey(QAbstractNativeEventFilter):
    """Calls `pressed` each time Ctrl+Space is pressed, wherever the focus is."""

    def __init__(self, pressed: Callable[[], None]) -> None:
        super().__init__()
        self.pressed = pressed

    def register(self) -> None:
        if not _user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_NOREPEAT, VK_SPACE):
            code = ctypes.get_last_error()
            if code == ERROR_HOTKEY_ALREADY_REGISTERED:
                raise HotkeyTaken("Ctrl+Space is already in use by another app")
            raise ctypes.WinError(code)

    def unregister(self) -> None:
        _user32.UnregisterHotKey(None, HOTKEY_ID)

    def nativeEventFilter(
        self, event_type: QByteArray | bytes | bytearray | memoryview, message: int, /
    ) -> object:
        """Qt passes every Windows message through here; ours is WM_HOTKEY with our id."""
        if QByteArray(event_type).data() != HOTKEY_EVENT_TYPE:
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
            self.pressed()
            return True, 0
        return False, 0
