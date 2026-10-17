"""Glance. Usage: pythonw glance.py [--config PATH]"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.ui.app import run

if __name__ == "__main__":
    app = QApplication(sys.argv[:1])  # lives until the end, so start-up errors can be shown
    raise SystemExit(run(app, Path(__file__).resolve().parent, sys.argv[1:]))
