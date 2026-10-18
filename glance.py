"""Glance. Usage: pythonw glance.py [--config PATH]"""

import shutil
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.herdr import Herdr, NoHerdr
from app.ui.app import run

if __name__ == "__main__":
    app = QApplication(sys.argv[:1])  # lives until the end, so start-up errors can be shown
    # Only its .exe: cmd.exe would run a .cmd one, and read a typed `&` or `%` as its own
    herdr = shutil.which("herdr.exe")
    agents = Herdr((herdr,)) if herdr else NoHerdr()
    raise SystemExit(run(app, Path(__file__).resolve().parent, sys.argv[1:], agents))
