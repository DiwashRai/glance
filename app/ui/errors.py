"""The one place errors are caught: Python's error hook, at the border with Qt.

PySide6 sends any error raised in our code while Qt is calling it (a key press, Enter, a timer,
an overridden Qt method) to `sys.excepthook`, and keeps running. Errors during start-up reach it
too, as the program ends. So nothing else in glance needs a `try`.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import QMessageBox


class ErrorHook:
    """Shows every error, then logs it to glance.log.

    `show` starts as a message box, for errors during start-up (the program then ends). Once the
    window exists, the app points `show` at it, and glance keeps going after an error.
    """

    def __init__(self) -> None:
        self.show: Callable[[str], None] = _message_box
        self.logger = logging.getLogger("glance")

    def install(self, log_path: Path) -> None:
        self.log_to(log_path)
        sys.excepthook = self

    def log_to(self, log_path: Path) -> None:
        """Logging handles its own file errors, so a log that can't be written hides nothing."""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8", delay=True)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self.logger.handlers = [handler]

    def __call__(self, _kind: type[BaseException], error: BaseException, _trace: object) -> None:
        """Matches `sys.excepthook`. The error carries its own traceback, so the rest is unused."""
        self.show(str(error) or type(error).__name__)
        self.logger.error("unhandled error", exc_info=error)


def _message_box(message: str) -> None:
    QMessageBox.critical(None, "glance", message)
