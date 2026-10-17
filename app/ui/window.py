"""The overlay: the lists as text, a text box, and a message line. Board F's look is PR 2c.

Ctrl+Space toggles it. Esc, or clicking anywhere else, hides it. It only talks to the
controller.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget

from app.controller import Controller, View
from app.core.model import Idle, LeftOff, Lists, ParkedTask, Task, Waiting


class Window(QWidget):
    def __init__(self, controller: Controller) -> None:
        super().__init__()
        self.controller = controller
        self.setWindowTitle("glance")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # no taskbar button
        )
        self.setFont(QFont("Consolas", 11))
        self.setMinimumWidth(640)
        self.lists = QLabel()
        self.input = QLineEdit()
        self.input.setPlaceholderText("what's going on?")
        self.message = QLabel()
        layout = QVBoxLayout(self)
        for widget in (self.lists, self.input, self.message):
            layout.addWidget(widget)
        self.input.returnPressed.connect(self.run)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.hide)

    def toggle(self) -> None:
        """Hide it if I'm using it; otherwise (hidden, or showing an error behind other
        windows) bring it up."""
        if self.isActiveWindow():
            self.hide()
        else:
            self.open()

    def open(self) -> None:
        """Re-read the lists, then show it in the middle of the screen, in front, ready to type."""
        self.draw(self.controller.open())
        self.adjustSize()
        self.move(self.screen().availableGeometry().center() - self.rect().center())
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def changeEvent(self, event: QEvent) -> None:
        """Clicking anywhere else hides it, like a menu."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.hide()

    def run(self) -> None:
        view = self.controller.run(self.input.text())
        if view.accepted:
            self.input.clear()
        self.draw(view)
        self.controller.write_history()  # after drawing, so a failure here can't leave it stale

    def draw(self, view: View) -> None:
        self.lists.setText(lists_text(view.lists))
        self.message.setText(view.problem or view.message)

    def show_error(self, message: str) -> None:
        """Called by the error hook. Redraws from what the controller holds (which is saved) and
        shows the window if it was hidden. It doesn't re-read tasks.md, so it can't fail again."""
        self.draw(View(self.controller.lists, f"error: {message}"))
        self.show()


def lists_text(lists: Lists) -> str:
    """Active, then Parked numbered the way `switch` counts them."""
    lines = ["Active", f"  {_active(lists.active)}", "", f"Parked {len(lists.parked)}"]
    for number, parked in enumerate(lists.parked, start=1):
        lines.append(f"  {number} {parked.task.title}")
        lines += _note(parked)
    return "\n".join(lines)


def _active(active: Task | Idle) -> str:
    match active:
        case Task(title=title):
            return title
        case Idle():
            return "nothing active · type a task"


def _note(parked: ParkedTask) -> list[str]:
    match parked.reason:
        case Waiting(on=on):
            return [f"      waiting on {on}"]
        case LeftOff(note=""):
            return []
        case LeftOff(note=note):
            return [f"      left off: {note}"]
