"""The overlay's pieces, as board F draws them: the Active card, the Parked card, the prompt with
its `›`, and the key hints.

Task text is always shown as plain text, never as HTML, and a line that doesn't fit ends in "…"
with the full text in a tooltip.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.model import CommandWords, Idle, LeftOff, ParkedTask, Task, Waiting
from app.ui import icons, theme
from app.ui.theme import font, label, restyle, styled

PARKED_ROWS = 6  # shown in full; the rest are "+N more"


def header(text: str, role: str = "header") -> QLabel:
    widget = label(text.upper(), role)
    widget.setFont(font(11, QFont.Weight.Medium, spacing=1.3))
    return widget


class Elided(QLabel):
    """One line of plain text that ends in "…" when it doesn't fit the width it's given, with
    the full text in a tooltip."""

    def __init__(self, role: str, size: int, weight: QFont.Weight = QFont.Weight.Normal) -> None:
        super().__init__()
        styled(self, role)
        self.setFont(font(size, weight))
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.full = ""

    def show_text(self, text: str) -> None:
        self.full = text
        self._fit()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit()

    def _fit(self) -> None:
        shown = self.fontMetrics().elidedText(self.full, Qt.TextElideMode.ElideRight, self.width())
        self.setText(shown)
        self.setToolTip(self.full if shown != self.full else "")


class ActiveCard(QFrame):
    """Orange, with a flame, when a task is active. A dashed empty slot when nothing is. The same
    height either way, so the text box under it never moves."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)
        self.top = QWidget()
        top = QHBoxLayout(self.top)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        flame = QLabel()
        flame.setPixmap(icons.pixmap(icons.FLAME, theme.ORANGE, 14))
        top.addWidget(flame)
        top.addWidget(header("Active", "active-header"))
        top.addStretch()
        self.title = Elided("title", 16, QFont.Weight.Medium)
        self.empty = label("nothing active · type a task, or s to switch to one", "dim")
        for widget in (self.top, self.title, self.empty):
            layout.addWidget(widget)
        orange_glow = QColor(theme.ORANGE)
        orange_glow.setAlpha(60)
        self.glow = QGraphicsDropShadowEffect(
            blurRadius=28, offset=QPointF(0, 0), color=orange_glow
        )
        self.setGraphicsEffect(self.glow)
        self.setFixedHeight(76)

    def show_active(self, active: Task | Idle) -> None:
        match active:
            case Task(title=title):
                self.title.show_text(title)
                self._mode("active", working=True)
            case Idle():
                self._mode("idle", working=False)

    def _mode(self, role: str, *, working: bool) -> None:
        restyle(self, "role", role)
        self.top.setVisible(working)
        self.title.setVisible(working)
        self.empty.setVisible(not working)
        self.glow.setEnabled(working)


class ParkedCard(QFrame):
    """Numbered the way `switch` counts, most recent first, with each task's note."""

    def __init__(self) -> None:
        super().__init__()
        styled(self, "card")
        self.setFixedWidth(340)
        self.list_layout = QVBoxLayout(self)
        self.list_layout.setContentsMargins(18, 14, 18, 16)
        self.list_layout.setSpacing(8)
        top = QHBoxLayout()
        self.header = header("Parked")
        top.addWidget(self.header)
        top.addStretch()
        top.addWidget(label("recent first", "dim", 11))
        self.list_layout.addLayout(top)
        self.list_layout.addStretch()  # rows go above this, so the card fills its column
        self.rows: list[QWidget] = []

    def show_parked(self, parked: tuple[ParkedTask, ...]) -> None:
        self.header.setText(f"Parked {len(parked)}".upper())
        for row in self.rows:
            self.list_layout.removeWidget(row)  # now, so it stops taking up space
            row.hide()
            row.deleteLater()
        self.rows = [_row(number, item) for number, item in enumerate(parked[:PARKED_ROWS], 1)]
        if not parked:
            self.rows.append(label("nothing parked", "dim"))
        if len(parked) > PARKED_ROWS:
            more = len(parked) - PARKED_ROWS
            self.rows.append(label(f"+{more} more · s <number> to switch", "dim", 12))
        for index, row in enumerate(self.rows):
            self.list_layout.insertWidget(1 + index, row)


def _row(number: int, parked: ParkedTask) -> QWidget:
    row = QWidget()
    layout = QVBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(1)
    top = QHBoxLayout()
    top.setSpacing(8)
    marker = QLabel()
    marker.setPixmap(_marker(parked.reason))
    title = Elided("title", 14)
    title.show_text(parked.task.title)
    top.addWidget(marker)
    top.addWidget(label(str(number), "number", 12))
    top.addWidget(title, stretch=1)
    layout.addLayout(top)
    note = _note(parked.reason)
    if note:
        sub = Elided("dim", 12)
        sub.setContentsMargins(36, 0, 0, 0)
        sub.show_text(note)
        layout.addWidget(sub)
    return row


def _note(reason: LeftOff | Waiting) -> str:
    match reason:
        case Waiting(on=on):
            return f"waiting on {on}"
        case LeftOff(note=""):
            return ""
        case LeftOff(note=note):
            return f"left off: {note}"


def _marker(reason: LeftOff | Waiting) -> QPixmap:
    """A yellow ring for waiting, a dashed grey ring for left off."""
    match reason:
        case Waiting():
            pen = QPen(QColor(theme.YELLOW), 2)
        case LeftOff():
            pen = QPen(QColor(theme.GREY_RING), 1.5)
            pen.setDashPattern([2, 2])
    pixmap = icons.blank(12)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(pen)
    painter.drawEllipse(2, 2, 8, 8)
    painter.end()
    return pixmap


class Prompt(QFrame):
    """The text box, with board F's blue `›`."""

    def __init__(self) -> None:
        super().__init__()
        styled(self, "prompt")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 13, 20, 13)
        layout.setSpacing(14)
        layout.addWidget(label("›", "prompt-mark", 22))
        self.input = QLineEdit()
        self.input.setFont(font(20))
        self.input.setPlaceholderText("what's going on?")
        layout.addWidget(self.input)


def message_line() -> QLabel:
    """Plain text, wrapped, in room for two lines, so a long message doesn't move anything."""
    widget = label("", "dim", 13)
    widget.setWordWrap(True)
    widget.setContentsMargins(22, 0, 22, 0)
    widget.setFixedHeight(widget.fontMetrics().lineSpacing() * 2 + 4)
    widget.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    return widget


def hints(words: CommandWords) -> QWidget:
    """`esc` close · `↵` run · the first word of each command."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(22, 0, 22, 0)
    layout.setSpacing(6)
    for key, does in (("esc", "close"), ("↵", "run")):
        layout.addWidget(label(key, "kbd", 11))
        layout.addWidget(label(does, "dim", 12))
        layout.addSpacing(10)
    first_words = Elided("dim", 12)
    first_words.show_text(
        " · ".join((words.park[0], words.switch[0], words.new[0], words.done[0], words.wait[0]))
    )
    layout.addWidget(first_words, stretch=1)
    return row
