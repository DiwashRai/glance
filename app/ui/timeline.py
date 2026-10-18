"""The Today card: an hour scale from an hour ago to three hours ahead, a bar for each stretch on a
task (orange for the one I'm on), and a line at now. Planned blocks and meetings join it later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from app.core.today import Day, Span, duration_text, total
from app.ui import theme
from app.ui.parts import header
from app.ui.theme import font, label, styled

BACK = timedelta(hours=1)  # how far back the scale starts
AHEAD = timedelta(hours=3)  # and how far ahead: any more and a half-hour is too thin to label
GUTTER = 44  # room for the hour labels, left of the bars
EDGE = 8  # so the top and bottom hour labels aren't cut in half
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class TodayCard(QFrame):
    def __init__(self, day: Day) -> None:
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
        self.timeline = Timeline(day)
        layout.addWidget(self.timeline, stretch=1)
        self.show_day(day)

    def show_day(self, day: Day) -> None:
        on_tasks = total(day.spans, day.since)
        shown = on_tasks >= timedelta(minutes=1)
        self.total.setText(f"{duration_text(on_tasks)} on tasks" if shown else "")
        self.timeline.day = day
        self.timeline.update()


@dataclass(frozen=True)
class Scale:
    """Where a time goes, top to bottom."""

    start: datetime
    end: datetime
    height: float

    def y(self, at: datetime) -> float:
        return EDGE + (at - self.start) / (self.end - self.start) * (self.height - 2 * EDGE)


class Timeline(QWidget):
    def __init__(self, day: Day) -> None:
        super().__init__()
        self.day = day

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.day.problem:
            painter.setPen(QColor(theme.RED))
            painter.setFont(font(12))
            painter.drawText(self.rect(), Qt.TextFlag.TextWordWrap, self.day.problem)
        elif self.height() > 4 * EDGE:  # room for a scale at all
            scale = Scale(self.day.now - BACK, self.day.now + AHEAD, self.height())
            self._hours(painter, scale)
            for span in self.day.spans:
                if span.end > scale.start:
                    self._bar(painter, scale, span)
            self._now(painter, scale)
        painter.end()

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

    def _bar(self, painter: QPainter, scale: Scale, span: Span) -> None:
        """The title goes in the bar when there's room for it."""
        top = scale.y(max(span.start, scale.start))
        # Inset half a pixel, so the 1px border isn't cut in half at the right edge
        right = self.width() - 0.5
        bar = QRectF(GUTTER + 4, top, right - GUTTER - 4, max(scale.y(span.end) - top, 2))
        edge, fill = (theme.ORANGE, theme.ACTIVE_CARD) if span.going else (theme.DIM, theme.PROMPT)
        painter.setPen(QPen(QColor(edge), 1))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(bar, 4, 4)
        painter.setFont(font(11))
        lines = painter.fontMetrics().lineSpacing()
        if bar.height() >= lines + 2:
            text = bar.adjusted(8, 1, -6, 0)
            title = painter.fontMetrics().elidedText(
                span.title, Qt.TextElideMode.ElideRight, int(text.width())
            )
            painter.setPen(QColor(theme.BRIGHT if span.going else theme.TEXT))
            painter.drawText(text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, title)

    def _now(self, painter: QPainter, scale: Scale) -> None:
        y = scale.y(self.day.now)
        painter.setPen(QPen(QColor(theme.BLUE), 1.5))
        painter.drawLine(QPointF(GUTTER, y), QPointF(self.width(), y))
        painter.setBrush(QColor(theme.BLUE))
        painter.drawEllipse(QPointF(GUTTER, y), 3, 3)
