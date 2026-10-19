"""The overlay's pieces, as board F draws them: the Active card, the Focus, Parked and Quick
cards, the prompt with its `›`, the key hints, and the card for a message for me.

Task text is always shown as plain text, never as HTML, and a line that doesn't fit ends in "…"
with the full text in a tooltip.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable

from PySide6.QtCore import QMimeData, QPointF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QInputMethodEvent,
    QKeyEvent,
    QPainter,
    QPen,
    QPixmap,
    QResizeEvent,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.commands import Preview, spaces_for
from app.core.model import (
    FOCUS_SLOTS,
    CommandWords,
    FromQuick,
    Idle,
    LeftOff,
    Message,
    ParkedTask,
    Task,
    Waiting,
    parked_note,
    shown,
    size_text,
    step_line,
    working,
)
from app.ui import icons, theme
from app.ui.theme import font, label, restyle, styled


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
        self.step = Elided("dim", 13)  # where it's up to: "rerun CI · 2/4"
        self.step.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.step, stretch=1)
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

    def show_active(self, active: Task | FromQuick | Idle) -> None:
        match working(active):
            case Task() as task:
                self.title.show_text(shown(task))
                self.step.show_text(step_line(task))
                self._mode("active", working=True)
            case Idle():
                self._mode("idle", working=False)

    def _mode(self, role: str, *, working: bool) -> None:
        restyle(self, "role", role)
        self.top.setVisible(working)
        self.title.setVisible(working)
        self.empty.setVisible(not working)
        self.glow.setEnabled(working)


class FocusCard(QFrame):
    """The one or two things the work is for, numbered the way `unfocus` counts. Hidden while
    there are none."""

    def __init__(self) -> None:
        super().__init__()
        styled(self, "card")
        self.setFixedWidth(340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(header("Focus"))
        top.addStretch()
        self.slots = label("", "dim", 11)
        top.addWidget(self.slots)
        layout.addLayout(top)
        self.rows: list[tuple[QWidget, Elided]] = []
        for number in range(1, FOCUS_SLOTS + 1):
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(8)
            title = Elided("title", 14)
            line.addWidget(label(str(number), "number", 12))
            line.addWidget(title, stretch=1)
            layout.addWidget(row)
            self.rows.append((row, title))

    def show_focus(self, focus: tuple[str, ...]) -> None:
        self.setVisible(bool(focus))
        self.slots.setText(f"{len(focus)} of {FOCUS_SLOTS}")
        for (row, title), text in zip(self.rows, (*focus, *[""] * FOCUS_SLOTS), strict=False):
            row.setVisible(bool(text))
            title.show_text(text)


class ListCard(QFrame):
    """A titled list that shows as many rows as fit in the height its column gives it, then
    "+N more". Parked and Quick are both one."""

    def __init__(self, name: str, corner: str, empty: str, more: str) -> None:
        super().__init__()
        styled(self, "card")
        # Its height comes from the column, never from its rows, so filling it can't resize it.
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Ignored)
        self.name, self.empty, self.more = name, empty, more
        self.list_layout = QVBoxLayout(self)
        self.list_layout.setContentsMargins(18, 14, 18, 16)
        self.list_layout.setSpacing(8)
        self.top = QWidget()
        top = QHBoxLayout(self.top)
        top.setContentsMargins(0, 0, 0, 0)
        self.header = header(name)
        top.addWidget(self.header)
        top.addStretch()
        top.addWidget(label(corner, "dim", 11))
        self.list_layout.addWidget(self.top)
        self.list_layout.addStretch()  # rows go above this, so the card fills its column
        self.rows: list[QWidget] = []
        self.count = 0
        self.row_at: Callable[[int], QWidget] = lambda _: QWidget()

    def show_rows(self, count: int, row_at: Callable[[int], QWidget]) -> None:
        """`row_at(i)` builds row i (from 0), only for the rows that fit."""
        self.count, self.row_at = count, row_at
        self.header.setText(f"{self.name} {count}".upper())
        self._fill()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fill()

    def _fill(self) -> None:
        for row in self.rows:
            self.list_layout.removeWidget(row)  # now, so it stops taking up space
            row.hide()
            row.deleteLater()
        self.rows = self._rows_that_fit()
        hidden = self.count - len(self.rows)
        if not self.count:
            self.rows.append(label(self.empty, "dim"))
        if hidden:
            self.rows.append(label(f"+{hidden} more · {self.more}", "dim", 12))
        for index, row in enumerate(self.rows):
            self.list_layout.insertWidget(1 + index, row)

    def _rows_that_fit(self) -> list[QWidget]:
        """Rows while they fit, keeping room for the "+N more" line under them."""
        margins = self.list_layout.contentsMargins()
        spacing = self.list_layout.spacing()
        room = self.height() - margins.top() - margins.bottom() - self.top.sizeHint().height()
        more = label("+", "dim", 12).sizeHint().height() + spacing
        rows: list[QWidget] = []
        for index in range(self.count):
            row = self.row_at(index)
            needed = row.sizeHint().height() + spacing
            last = index == self.count - 1
            if needed + (0 if last else more) > room:
                row.deleteLater()
                break
            room -= needed
            rows.append(row)
        return rows


def parked_card() -> ListCard:
    """Numbered the way `switch` counts, most recent first, with each task's note."""
    card = ListCard("Parked", "recent first", "nothing parked", "s <number> to switch")
    card.setFixedWidth(340)
    return card


def show_parked(card: ListCard, parked: tuple[ParkedTask, ...]) -> None:
    card.show_rows(len(parked), lambda index: _row(index + 1, parked[index]))


def quick_card() -> ListCard:
    """Small things to do while a build or an agent runs, smallest first, numbered q1, q2…"""
    card = ListCard("Quick", "while you wait", "nothing quick · quick <what> ~5m", "done q<n>")
    card.setFixedWidth(300)
    return card


def show_quick(card: ListCard, quick: tuple[Task, ...]) -> None:
    card.show_rows(len(quick), lambda index: _quick_row(index + 1, quick[index]))


def _quick_row(number: int, task: Task) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    title = Elided("title", 14)
    title.show_text(task.title)
    layout.addWidget(label(f"q{number}", "number", 12))
    layout.addWidget(title, stretch=1)
    layout.addWidget(label(size_text(task), "dim", 12))
    return row


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
    title.show_text(shown(parked.task))
    top.addWidget(marker)
    top.addWidget(label(str(number), "number", 12))
    top.addWidget(title, stretch=1)
    layout.addLayout(top)
    note = parked_note(parked)
    if note:
        sub = Elided("dim", 12)
        sub.setContentsMargins(36, 0, 0, 0)
        sub.show_text(note)
        layout.addWidget(sub)
    return row


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


NOTE_WIDTH = 260
MAX_LINES = 5  # then it scrolls
# What Python counts as a line break, and a tab, which a pane may read as a key of its own
LINE_BREAK = re.compile(r"\r\n|[\t\n\r\v\f\x1c-\x1e\x85\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}]")


class Box(QPlainTextEdit):
    """What I type: one line that wraps, and grows to MAX_LINES as it does. Enter sends it
    (`sent`). A line break that comes in another way (a paste, an input method, dictation)
    becomes a space as it comes in, as an agent's pane would read it as Enter. Tab does
    nothing: there's nowhere else to go."""

    sent = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setFont(font(16))
        self.setPlaceholderText("what's going on?")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(0)
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self.line = self.fontMetrics().lineSpacing()
        self.setFixedHeight(self.line)

    def text(self) -> str:
        """One line, even if a break got in some way not caught below."""
        return LINE_BREAK.sub(" ", self.toPlainText())

    def insertFromMimeData(self, source: QMimeData) -> None:
        """A paste or a drop."""
        self.insertPlainText(LINE_BREAK.sub(" ", source.text()))

    def inputMethodEvent(self, e: QInputMethodEvent) -> None:
        """An input method or dictation, with the word it's still composing left as it is."""
        flat = QInputMethodEvent(e.preeditString(), e.attributes())
        commit = LINE_BREAK.sub(" ", e.commitString())
        flat.setCommitString(commit, e.replacementStart(), e.replacementLength())
        super().inputMethodEvent(flat)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        match e.key():
            case Qt.Key.Key_Return | Qt.Key.Key_Enter:
                self.sent.emit()
            case Qt.Key.Key_Tab | Qt.Key.Key_Backtab:
                pass
            case _:
                super().keyPressEvent(e)

    def resizeEvent(self, e: QResizeEvent) -> None:
        """The note coming and going changes the width, and so how many lines it wraps to."""
        super().resizeEvent(e)
        self._fit()

    def _fit(self) -> None:
        """As tall as the lines it wraps to, up to MAX_LINES, measured where Qt laid them out,
        with the cursor kept in sight. The extra pixel is for Qt, which counts a line ending
        exactly on the bottom edge as cut off, and would keep the first line scrolled away."""
        block = self.document().firstBlock()
        tall = self.blockBoundingRect(block).height()  # lays the line out, if it isn't yet
        lines = block.layout().lineCount()
        self.setFixedHeight(math.ceil(tall * min(lines, MAX_LINES) / lines) + 1)
        self.ensureCursorVisible()


class Prompt(QFrame):
    """The text box, with board F's blue `›`. As I type, the words glance picked up are blue, and
    a note on the right says what else will happen. For an agent, the `›` and the note (its name)
    turn yellow, or the note is red if it can't be sent to. The `›` and the note stay level with
    the first line as the box grows."""

    def __init__(self) -> None:
        super().__init__()
        styled(self, "prompt")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 13, 20, 13)
        layout.setSpacing(14)
        self.input = Box()
        self.mark = label("›", "prompt-mark", 18)
        self.note = label("", "dim", 13)
        for widget, stretch in ((self.mark, 0), (self.input, 1), (self.note, 0)):
            widget.setMinimumHeight(self.input.line)  # the labels: centred on the first line
            layout.addWidget(widget, stretch, Qt.AlignmentFlag.AlignTop)

    def show_preview(self, preview: Preview) -> None:
        """The note never takes more than NOTE_WIDTH, so what's typed keeps its room."""
        note = preview.note
        fitted = self.note.fontMetrics().elidedText(note, Qt.TextElideMode.ElideRight, NOTE_WIDTH)
        self.note.setText(fitted)
        agent = "agent" if preview.agent else ""
        restyle(self.mark, "tone", agent)
        restyle(self.note, "tone", "error" if preview.trouble else agent)
        _colour(self.input, preview.marks)


def _colour(box: Box, marks: tuple[tuple[int, int], ...]) -> None:
    text = box.text()
    box.setExtraSelections([_picked(box, _utf16(text, s), _utf16(text, e)) for s, e in marks])


def _picked(box: Box, start: int, end: int) -> QTextEdit.ExtraSelection:
    """The text from `start` to `end`, coloured blue."""
    cursor = QTextCursor(box.document())
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    blue = QTextCharFormat()
    blue.setForeground(QColor(theme.BLUE))
    picked = QTextEdit.ExtraSelection()
    picked.cursor, picked.format = cursor, blue  # set whole: Qt hands back copies
    return picked


def _utf16(text: str, index: int) -> int:
    """Where Python's `index` is in Qt's count, which is in UTF-16 units: an emoji is two."""
    return len(text[:index].encode("utf-16-le", "surrogatepass")) // 2  # half an emoji, pasted


def message_line() -> QLabel:
    """Plain text, wrapped, in room for two lines, so a long message doesn't move anything."""
    widget = label("", "dim", 13)
    widget.setWordWrap(True)
    widget.setContentsMargins(4, 0, 4, 0)
    widget.setFixedHeight(widget.fontMetrics().lineSpacing() * 2 + 4)
    widget.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    return widget


class InboxCard(QFrame):
    """The oldest message for me, edged in yellow, under the prompt: who it's from, when, how
    many are waiting, then the keys that clear it or answer it. As tall as its text wraps to at
    the width it's given. Hidden while there are none."""

    def __init__(self) -> None:
        super().__init__()
        styled(self, "inbox")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(8)
        self.who = header("", "inbox-header")
        self.at = label("", "number", 12)
        self.count = label("", "dim", 11)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self.who)
        top.addWidget(self.at)
        top.addStretch()
        top.addWidget(self.count)
        self.text = label("", "title", 14)
        self.text.setWordWrap(True)
        self.spaces = label("", "kbd", 11)  # ␣␣ for chief, ␣ for assistant
        self.reply = label("reply", "dim", 12)
        keys = QHBoxLayout()
        keys.setSpacing(6)
        for widget in (label("↵", "kbd", 11), label("clear", "dim", 12)):
            keys.addWidget(widget)
        keys.addSpacing(10)
        keys.addWidget(self.spaces)
        keys.addWidget(self.reply)
        keys.addStretch()
        layout.addLayout(top)
        layout.addWidget(self.text)
        layout.addLayout(keys)
        self.hide()

    def show_inbox(self, inbox: tuple[Message, ...], words: CommandWords) -> None:
        """Answering is offered only to a sender that lines can go to."""
        self.setVisible(bool(inbox))
        if not inbox:
            return
        top = inbox[0]
        self.who.setText(f"● from {top.sender}".upper())
        self.at.setText(top.at)
        self.count.setText(f"1 of {len(inbox)}" if len(inbox) > 1 else "")
        self.text.setText(top.text)
        spaces = spaces_for(top.sender, words)
        self.spaces.setText("␣" * spaces)
        self.spaces.setVisible(bool(spaces))
        self.reply.setVisible(bool(spaces))


def hints(words: CommandWords) -> QWidget:
    """`esc` close · `↵` run · the first word of each command."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(4, 0, 4, 0)
    layout.setSpacing(6)
    for key, does in (("esc", "close"), ("↵", "run")):
        layout.addWidget(label(key, "kbd", 11))
        layout.addWidget(label(does, "dim", 12))
        layout.addSpacing(10)
    first_words = Elided("dim", 12)
    commands = (
        words.park,
        words.switch,
        words.done,
        words.wait,
        words.focus,
        words.quick,
    )
    first_words.show_text(" · ".join(command[0] for command in commands))
    layout.addWidget(first_words, stretch=1)
    return row
