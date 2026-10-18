"""The overlay, laid out as board F: Focus above Parked on the left; Active, the prompt, the
message line and the key hints in the middle; Today above Quick on the right.
The cards float over the screen, which is dimmed behind them.

Ctrl+Space opens it to type; held, it's a peek that hides when the keys are let go. Ctrl+Space
again, Esc, or clicking anywhere else, hides it. It only talks to the controller.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QElapsedTimer, QEvent, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QHideEvent, QKeySequence, QMouseEvent, QShortcut
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from app.controller import Controller, View
from app.ui import parts, theme
from app.ui.theme import styled
from app.ui.timeline import TodayCard
from app.win32.hotkey import held

SIZE = QSize(1380, 480)  # board F's proportions
PEEK_MS = 300  # Ctrl+Space held this long is a peek, not a tap
WATCH_MS = 20  # how often the keys are checked while they're down


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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # the cards float
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)  # a peek leaves the focus
        self.setStyleSheet(theme.STYLESHEET)
        self.backdrop = Backdrop(self.hide)

        self.focus = parts.FocusCard()
        self.parked = parts.parked_card()
        self.quick = parts.quick_card()
        self.today = TodayCard(controller.day(), controller.words.block[0])
        self.active = parts.ActiveCard()
        self.prompt = parts.Prompt()
        self.message = parts.message_line()
        self.input = self.prompt.input
        self._lay_out(parts.hints(controller.words))

        self.held_for = QElapsedTimer()
        self.peeking = False  # the keys were seen down at PEEK_MS
        self.focusing = False  # asked Windows for the focus, not granted yet
        self.watch = QTimer(self)
        self.watch.setInterval(WATCH_MS)
        self.watch.timeout.connect(self._watch_keys)
        self.input.returnPressed.connect(self.run)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.hide)

    def _lay_out(self, hints: QWidget) -> None:
        centre = styled(QFrame(), "card")  # Active, the prompt, the message and the hints
        inside = QVBoxLayout(centre)
        inside.setContentsMargins(20, 20, 20, 16)
        inside.setSpacing(12)
        for widget in (self.active, self.prompt, self.message, hints):
            inside.addWidget(widget)
        # As tall as everything it holds, measured once styled; it never grows or shrinks
        centre.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        middle = QVBoxLayout()
        middle.addStretch()
        middle.addWidget(centre)
        middle.addStretch()
        panel = styled(QFrame(), "panel")
        columns = QHBoxLayout(panel)
        columns.setContentsMargins(40, 40, 40, 40)
        columns.setSpacing(40)
        left = QVBoxLayout()
        left.setSpacing(16)
        left.addWidget(self.focus)
        left.addWidget(self.parked, stretch=1)
        columns.addLayout(left)
        columns.addLayout(middle, stretch=1)
        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(self.today, stretch=2)
        right.addWidget(self.quick, stretch=1)  # the top few, then "+N more"
        columns.addLayout(right)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

    def pressed(self) -> None:
        """Ctrl+Space. If I'm using it, or the last press hasn't settled (still watched, or its
        focus not yet granted: a quick second tap), it hides. Otherwise it shows straight away,
        without the focus, and the keys decide: let go within PEEK_MS and it takes the focus,
        ready to type; still down at PEEK_MS and it's a peek, gone when they're let go."""
        if self.isActiveWindow() or self.watch.isActive() or self.focusing:
            self.hide()
            return
        self.peeking = False
        self.held_for.start()
        self._appear()
        self.watch.start()

    def _watch_keys(self) -> None:
        """A peek only if the keys were seen still down at PEEK_MS, so a slow first show can't
        turn a tap into one."""
        if held():
            self.peeking = self.held_for.elapsed() >= PEEK_MS
            return
        self.watch.stop()
        if self.peeking:
            self.hide()
        else:
            self._take_focus()

    def open(self) -> None:
        """Show it, ready to type: from the tray icon or the HUD. It takes over from a peek."""
        self.watch.stop()
        self._appear()
        self._take_focus()

    def _appear(self) -> None:
        """Re-read the lists, then show it in the middle of the screen under the mouse, in front,
        without taking the focus."""
        self.draw(self.controller.open())
        area = (QGuiApplication.screenAt(QCursor.pos()) or self.screen()).availableGeometry()
        self.setFixedSize(SIZE.boundedTo(area.size()))  # never jumps; smaller on a small screen
        self.move(area.center() - self.rect().center())
        self.backdrop.cover(area)
        self.show()
        self.raise_()

    def _take_focus(self) -> None:
        self.focusing = True  # until Windows grants it, or the window hides
        self.activateWindow()
        self.input.setFocus()
        self.input.selectAll()  # leftover text is selected, so typing replaces it

    def changeEvent(self, event: QEvent) -> None:
        """Clicking anywhere else hides it, like a menu. Clicking into a peek keeps it open: the
        keys no longer decide."""
        super().changeEvent(event)
        if event.type() != QEvent.Type.ActivationChange:
            return
        if self.isActiveWindow():
            self.watch.stop()
            self.focusing = False
        else:
            self.hide()

    def hideEvent(self, event: QHideEvent) -> None:
        """However it hides, the last press is over, and the screen behind is undimmed."""
        super().hideEvent(event)
        self.watch.stop()
        self.focusing = False
        self.backdrop.hide()

    def run(self) -> None:
        view = self.controller.run(self.input.text())
        if view.accepted:
            self.input.clear()
        self.draw(view)
        self.controller.write_history()  # after drawing, so a failure here can't leave it stale

    def draw(self, view: View) -> None:
        self.active.show_active(view.lists.active)
        self.focus.show_focus(view.lists.focus)
        parts.show_parked(self.parked, view.lists.parked)
        parts.show_quick(self.quick, view.lists.quick)
        self.today.show_day(self.controller.day())
        self._say(view.problem or view.message, _tone(view))

    def show_error(self, message: str) -> None:
        """Called by the error hook. Redraws from what the controller holds (which is saved) and
        shows the window if it was hidden. It doesn't re-read tasks.md, so it can't fail again."""
        self.draw(View(self.controller.lists))
        self._say(f"error: {message}", "error")
        self.watch.stop()  # an error turns a peek into a window that stays
        self.backdrop.cover(self.screen().availableGeometry())
        self.show()
        self.raise_()

    def _say(self, text: str, tone: str) -> None:
        self.message.setText(text)
        theme.restyle(self.message, "tone", tone)


class Backdrop(QWidget):
    """The screen behind the overlay, dimmed, so the cards float over it. It never takes the
    focus, and a click on it closes the overlay, however the overlay was opened. The taskbar
    (with the HUD) isn't dimmed. Nothing runs while it's up."""

    def __init__(self, clicked: Callable[[], None]) -> None:
        super().__init__()
        self.clicked = clicked
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # no taskbar button
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("background: black;")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setWindowOpacity(theme.BACKDROP_DIM)

    def cover(self, area: QRect) -> None:
        """Shown over `area`, under the overlay (which is shown after it)."""
        self.setGeometry(area)
        self.show()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """On release, not press, so the release can't land on the app underneath."""
        super().mouseReleaseEvent(event)
        self.clicked()


def _tone(view: View) -> str:
    """The message line's colour: plain for a change, orange for a refusal, red for a problem."""
    if view.problem:
        return "error"
    return "done" if view.accepted else "refused"
