"""The Today card: an hour scale from an hour ago to three hours ahead, today's planned blocks as
quiet outlines, a bar for each stretch on a task (orange for the one I'm on) drawn over them, and a
line at now. Meetings join it later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from app.core.today import Day, Slot, Span, duration_text, total
from app.ui import theme
from app.ui.parts import header
from app.ui.theme import font, label, styled

BACK = timedelta(hours=1)  # how far back the scale starts
AHEAD = timedelta(hours=3)  # and how far ahead: any more and a half-hour is too thin to label
GUTTER = 44  # room for the hour labels, left of the bars
EDGE = 8  # so the top and bottom hour labels aren't cut in half
INSET = 6  # a bar sits this far inside a block, so the block's edges show around it
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class TodayCard(QFrame):
    def __init__(self, day: Day, plan_word: str) -> None:
        super().__init__()
        styled(self, "card")
        self.setFixedWidth(300)
        # Its height comes from the column, like Parked and Quick
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Ignored)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(header("Today"))
        top.addStretch()
        self.total = label("", "dim", 11)
        top.addWidget(self.total)
        layout.addLayout(top)
        self.timeline = Timeline(day, plan_word)
        layout.addWidget(self.timeline, stretch=1)
        self.problem = label("", "dim", 12)  # why events.log can't be read: the plan still shows
        self.problem.setWordWrap(True)
        theme.restyle(self.problem, "tone", "error")
        layout.addWidget(self.problem)
        self.show_day(day)

    def show_day(self, day: Day) -> None:
        on_tasks = total(day.spans, day.since)
        shown = on_tasks >= timedelta(minutes=1)
        self.total.setText(f"{duration_text(on_tasks)} on tasks" if shown else "")
        self.timeline.day = day
        self.timeline.update()
        self.problem.setText(day.problem)
        self.problem.setVisible(bool(day.problem))


@dataclass(frozen=True)
class Scale:
    """Where a time goes, top to bottom."""

    start: datetime
    end: datetime
    height: float

    def y(self, at: datetime) -> float:
        return EDGE + (at - self.start) / (self.end - self.start) * (self.height - 2 * EDGE)


class Timeline(QWidget):
    def __init__(self, day: Day, plan_word: str) -> None:
        super().__init__()
        self.day = day
        self.plan_word = plan_word  # the block command's first word

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.height() > 4 * EDGE:  # room for a scale at all
            self._scale(painter, Scale(self.day.now - BACK, self.day.now + AHEAD, self.height()))
        painter.end()

    def _scale(self, painter: QPainter, scale: Scale) -> None:
        self._hours(painter, scale)
        for slot in self.day.slots:
            if slot.end > scale.start and slot.start < scale.end:
                self._block(painter, scale, slot)
        for span in self.day.spans:
            if span.end > scale.start:
                self._bar(painter, scale, span)
        if not self.day.slots:  # how to plan, where the plan would go
            below = self._track(scale.y(self.day.now) + 6, self.height())
            _label(painter, below, f"{self.plan_word} 14:00 1h <what>", theme.DIM)
        self._now(painter, scale)

    def _hours(self, painter: QPainter, scale: Scale) -> None:
        """Each whole hour on the scale: its time, and a faint line across."""
        painter.setFont(font(11))
        first = scale.start.replace(minute=0, second=0, microsecond=0)
        if first < scale.start:
            first += timedelta(hours=1)
        for hour in range(int((scale.end - first) / timedelta(hours=1)) + 1):
            at = first + timedelta(hours=hour)
            y = scale.y(at)
            painter.setPen(QColor(theme.NUMBER))
            local = at.astimezone()  # the zone's own hour, on the night the clocks change too
            painter.drawText(QRectF(0, y - 8, GUTTER - 8, 16), _RIGHT, f"{local:%H:%M}")
            painter.setPen(QPen(QColor(theme.BORDER), 1))
            painter.drawLine(QPointF(GUTTER, y), QPointF(self.width(), y))

    def _track(self, top: float, bottom: float, inset: float = 0) -> QRectF:
        """Across the scale, right of the hour labels. Half a pixel in from the right, so a 1px
        border isn't cut in half there."""
        left, right = GUTTER + 4 + inset, self.width() - 0.5 - inset
        return QRectF(left, top, right - left, max(bottom - top, 2))

    def _block(self, painter: QPainter, scale: Scale, slot: Slot) -> None:
        """Drawn to its real times, so one running off the scale doesn't look as if it ends at
        the edge. Its number and name go at the top of what's still to come of it, so the block
        I'm in stays named below the now line."""
        top = scale.y(max(slot.start, scale.start))
        block = self._track(scale.y(slot.start), scale.y(slot.end))
        tint = QColor(theme.BLUE)
        tint.setAlpha(24)
        edge = QColor(theme.BLUE)
        edge.setAlpha(150)
        painter.setPen(QPen(edge, 1))
        painter.setBrush(tint)
        painter.drawRoundedRect(block, 6, 6)
        must = " !" if slot.block.must else ""
        label_top = max(top, scale.y(self.day.now)) + 2
        bottom = min(block.bottom(), self.height())  # only what's on the card has room for it
        named = QRectF(block.left(), label_top, block.width(), bottom - label_top)
        _label(painter, named, f"{slot.number}  {slot.block.what}", theme.BLUE, must)

    def _bar(self, painter: QPainter, scale: Scale, span: Span) -> None:
        """The title goes in the bar when there's room for it."""
        top = scale.y(max(span.start, scale.start))
        bar = self._track(top, scale.y(span.end), INSET)
        going = (theme.ORANGE, theme.ACTIVE_CARD, theme.BRIGHT)
        edge, fill, words = going if span.going else (theme.DIM, theme.PROMPT, theme.TEXT)
        painter.setPen(QPen(QColor(edge), 1))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(bar, 4, 4)
        _label(painter, bar.adjusted(0, 1, 0, 0), span.title, words)

    def _now(self, painter: QPainter, scale: Scale) -> None:
        y = scale.y(self.day.now)
        painter.setPen(QPen(QColor(theme.BLUE), 1.5))
        painter.drawLine(QPointF(GUTTER, y), QPointF(self.width(), y))
        painter.setBrush(QColor(theme.BLUE))
        painter.drawEllipse(QPointF(GUTTER, y), 3, 3)


def _label(painter: QPainter, room: QRectF, text: str, colour: str, keep: str = "") -> None:
    """One line at the top left of `room`, ending in "…" if it's too long, and left out if
    there isn't a line's height. `keep` goes on the end even when the text is cut short."""
    painter.setFont(font(11))
    metrics = painter.fontMetrics()
    if room.height() < metrics.lineSpacing() + 1:
        return
    line = room.adjusted(8, 0, -6, 0)
    width = int(line.width()) - metrics.horizontalAdvance(keep)
    shown = metrics.elidedText(text, Qt.TextElideMode.ElideRight, width) + keep
    painter.setPen(QColor(colour))
    painter.drawText(line, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, shown)
