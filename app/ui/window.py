"""The overlay, laid out as board F: Parked on the left; Active, the prompt, the message line and
the key hints in the middle. The time side (Today, Quick) comes later.

Ctrl+Space toggles it. Esc, or clicking anywhere else, hides it. It only talks to the
controller.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QCursor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from app.controller import Controller, View
from app.ui import parts, theme
from app.ui.theme import styled

SIZE = QSize(1040, 480)  # board F's proportions, without the time column


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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # for the rounded panel
        self.setStyleSheet(theme.STYLESHEET)

        self.parked = parts.ParkedCard()
        self.active = parts.ActiveCard()
        self.prompt = parts.Prompt()
        self.message = parts.message_line()
        self.input = self.prompt.input
        self._lay_out(parts.hints(controller.words))

        self.input.returnPressed.connect(self.run)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.hide)

    def _lay_out(self, hints: QWidget) -> None:
        middle = QVBoxLayout()
        middle.setSpacing(12)
        middle.addStretch()
        for widget in (self.active, self.prompt, self.message, hints):
            middle.addWidget(widget)
        middle.addStretch()
        panel = styled(QFrame(), "panel")
        columns = QHBoxLayout(panel)
        columns.setContentsMargins(40, 40, 40, 40)
        columns.setSpacing(40)
        columns.addWidget(self.parked)
        columns.addLayout(middle, stretch=1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

    def toggle(self) -> None:
        """Hide it if I'm using it; otherwise (hidden, or showing an error behind other
        windows) bring it up."""
        if self.isActiveWindow():
            self.hide()
        else:
            self.open()

    def open(self) -> None:
        """Re-read the lists, then show it in the middle of the screen under the mouse, in front,
        ready to type."""
        self.draw(self.controller.open())
        area = (QGuiApplication.screenAt(QCursor.pos()) or self.screen()).availableGeometry()
        self.setFixedSize(
            SIZE.boundedTo(area.size())
        )  # fixed, so it never jumps; smaller on a small screen
        self.move(area.center() - self.rect().center())
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        self.input.selectAll()  # leftover text is selected, so typing replaces it

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
        self.active.show_active(view.lists.active)
        self.parked.show_parked(view.lists.parked)
        self._say(view.problem or view.message, _tone(view))

    def show_error(self, message: str) -> None:
        """Called by the error hook. Redraws from what the controller holds (which is saved) and
        shows the window if it was hidden. It doesn't re-read tasks.md, so it can't fail again."""
        self.draw(View(self.controller.lists))
        self._say(f"error: {message}", "error")
        self.show()

    def _say(self, text: str, tone: str) -> None:
        self.message.setText(text)
        theme.restyle(self.message, "tone", tone)


def _tone(view: View) -> str:
    """The message line's colour: plain for a change, orange for a refusal, red for a problem."""
    if view.problem:
        return "error"
    return "done" if view.accepted else "refused"
