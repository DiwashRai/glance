"""Starts glance: settings, the single-instance lock, the error hook, the store, then the shell
(the window, the tray icon and Ctrl+Space)."""

from __future__ import annotations

import argparse
import os
import signal
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication

from app.config import default_config, load_settings
from app.controller import Agents, Controller
from app.store import Store
from app.ui.errors import ErrorHook
from app.ui.shell import Shell


class AlreadyRunning(RuntimeError):
    pass


def run(app: QApplication, home: Path, argv: list[str], agents: Agents) -> int:
    """`home` is where glance lives: the folder with config.toml. `agents` are the ones a line
    starting with spaces is sent to (herdr's).

    The entry point owns `app`, so it outlives this function: a start-up error unwinds `run`,
    and the error hook still needs a live QApplication to show its message box.
    """
    hook = ErrorHook()
    hook.install(Path(os.environ["LOCALAPPDATA"]) / "glance" / "glance.log")

    settings = load_settings(config_path(home, argv))
    settings.data_folder.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(settings.data_folder / "glance.lock"))
    if not lock.tryLock(0):
        raise AlreadyRunning("glance is already running")
    hook.log_to(settings.data_folder / "glance.log")

    controller = Controller(Store(settings.data_folder), settings.words, _now, agents)
    # Read now, so an error before the overlay first opens (a bad counts file, say) is shown
    # over the real lists and today's history, not empty ones
    controller.open()
    shell = Shell(app, controller, settings.hud, settings.counts_file)
    shell.start()
    # Only now do errors go to the window: one during start-up (Ctrl+Space taken, say) must
    # reach the message box, not a hidden window.
    hook.show = shell.window.show_error
    # Ctrl+C in the terminal quits cleanly (freeing Ctrl+Space and the lock), rather than
    # surfacing as an error in whatever Python code Qt happens to be running.
    signal.signal(signal.SIGINT, lambda _signal, _frame: app.quit())
    # Python only notices a signal when it runs Python code, and an idle Qt loop runs none.
    # Waking twice a second lets Ctrl+C land straight away.
    wake = QTimer()
    wake.timeout.connect(lambda: None)
    wake.start(500)

    code = app.exec()
    lock.unlock()
    return code


def config_path(home: Path, argv: list[str]) -> Path:
    """`--config` if given, else config.local.toml if it exists, else config.toml."""
    parser = argparse.ArgumentParser(prog="glance", add_help=False, exit_on_error=False)
    parser.add_argument("--config", default="")
    known, unknown = parser.parse_known_args(argv)
    if unknown:
        raise ValueError(f"unknown arguments: {' '.join(unknown)}. Usage: glance [--config PATH]")
    chosen: str = known.config
    return Path(chosen) if chosen else default_config(home)


def _now() -> datetime:
    """Local time with its UTC offset. The only clock read the lists ever see."""
    return datetime.now(UTC).astimezone()
