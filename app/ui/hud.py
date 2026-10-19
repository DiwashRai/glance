"""The HUD: one row on every taskbar, just left of the tray on the main one and of the clock on
the others. Each count from the collector is a chip: its icon or label and its number, coloured
by its source and its level. The main taskbar's row starts with the active task (optional): the
others are narrower, and the app buttons come close. While messages for me are waiting, a yellow
chip goes before the counts: who the top one's from, and how many more.

Every 2 seconds, and when a monitor comes or goes, it finds the taskbars showing, sits on each
and lifts itself back above them. One hides with its taskbar (a full-screen video or game on
that monitor, or auto-hide). It only redraws when what it shows has changed. Clicking any of
them opens the overlay.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QMouseEvent, QScreen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from app.core.model import HudSettings, Idle, Lists, Message, Task, step_line, working
from app.counts import Count, CountsFile
from app.ui import icons, theme
from app.win32.taskbar import Tray, find_taskbars, lift, light_taskbar

TICK_MS = 2000
GAP = 8  # between the HUD and the tray, in Qt pixels
HEIGHT_SHARE = 0.7  # of the taskbar's height
ACTIVE_WIDTH = 220  # the most the active title takes
MIN_ACTIVE_WIDTH = 80  # less room than this and the title is left out
MAX_SHARE = 0.25  # of the taskbar's width, to stay clear of the app buttons


@dataclass(frozen=True)
class Shown:
    """What the HUD is showing, so it only redraws when this changes."""

    active: str
    counts: tuple[Count, ...]
    light: bool
    inbox: tuple[Message, ...] = ()
    room: int = 0  # the most the HUD may take, in Qt pixels


class Hud:
    """A bar on each taskbar, all showing the same. A bar is made when a taskbar first appears,
    and hides with it."""

    def __init__(
        self,
        settings: HudSettings,
        lists: Callable[[], Lists],
        inbox: Callable[[], tuple[Message, ...]],
        counts_file: Path,
        clicked: Callable[[], None],
    ) -> None:
        self.settings = settings
        self.lists = lists
        self.inbox = inbox
        self.counts = CountsFile(counts_file)
        self.clicked = clicked
        self.bars: list[_Bar] = []
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)

    def start(self) -> None:
        """The first check runs once the app is running, so a problem in it (a bad counts file,
        say) is shown in the overlay instead of stopping glance from starting."""
        QTimer.singleShot(0, self.tick)
        self.timer.start(TICK_MS)

    def tick(self) -> None:
        trays = find_taskbars()
        while len(self.bars) < len(trays):
            self.bars.append(_Bar(self.settings, self.clicked))
        showing = [(bar, tray) for bar, tray in zip(self.bars, trays, strict=False) if tray.showing]
        for bar in set(self.bars) - {bar for bar, _ in showing}:
            bar.hide()
        if showing:
            active = _active_title(working(self.lists().active))
            shown = Shown("", self.counts.read(), light_taskbar(), self.inbox())
            for bar, tray in showing:
                bar.show_on(tray, replace(shown, active=active) if tray.main else shown)


class _Bar(QWidget):
    """The HUD on one taskbar."""

    def __init__(self, settings: HudSettings, clicked: Callable[[], None]) -> None:
        super().__init__()
        self.settings = settings
        self.clicked = clicked
        self.shown = Shown("", (), light=False)
        self.setWindowTitle("glance HUD")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # no taskbar button
            | Qt.WindowType.WindowDoesNotAcceptFocus  # clicking it never takes the focus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)  # it's never the active window
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.frame = QFrame(self)
        self.frame.setObjectName("hud")  # so the box style applies to the box, not its contents
        self.row = QHBoxLayout(self.frame)
        self.row.setContentsMargins(10, 0, 10, 0)
        self.row.setSpacing(8)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.frame)
        self.items: list[QWidget] = []

    def show_on(self, tray: Tray, shown: Shown) -> None:
        screen = _screen(tray)
        shown = replace(shown, room=int(tray.width / screen.devicePixelRatio() * MAX_SHARE))
        if shown != self.shown:
            self.shown = shown
            self._draw(shown)
        self._place(tray, screen)
        self.show()
        lift(int(self.winId()))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked()

    def _draw(self, shown: Shown) -> None:
        """The chips go in first. The active task then goes in front of them, shortened to the
        room they leave, or left out if there's too little."""
        for item in self.items:
            self.row.removeWidget(item)
            item.hide()
            item.deleteLater()
        style = _Style.of(self.settings, light=shown.light)
        self.frame.setStyleSheet(f"QFrame#hud {{ {style.frame} }}")
        active = shown.active if self.settings.show_active else ""
        self.items = _chips(shown, self.settings, style, calm=not active)
        for item in self.items:
            self.row.addWidget(item, alignment=Qt.AlignmentFlag.AlignVCenter)  # its own height
            item.show()  # now, so its width counts when the HUD is measured and placed
        used = sum(item.sizeHint().width() + self.row.spacing() for item in self.items)
        room = min(ACTIVE_WIDTH, shown.room - used)
        if active and room >= MIN_ACTIVE_WIDTH:
            self.items.insert(0, _active(active, style, room))
            self.row.insertWidget(0, self.items[0], alignment=Qt.AlignmentFlag.AlignVCenter)
            self.items[0].show()

    def _place(self, tray: Tray, screen: QScreen) -> None:
        """Tray rectangles are in real pixels. Qt keeps each screen's top-left corner where it
        really is, and scales what's inside it by the screen's own factor."""
        origin, scale = screen.geometry().topLeft(), screen.devicePixelRatio()
        height = int(tray.height / scale * HEIGHT_SHARE)
        self.setFixedHeight(height)
        self.adjustSize()
        x = origin.x() + int((tray.left - origin.x()) / scale) - self.width() - GAP
        y = origin.y() + int((tray.top + tray.height / 2 - origin.y()) / scale - height / 2)
        self.move(x, y)


def _screen(tray: Tray) -> QScreen:
    """The screen a taskbar is on, found by where it really is."""
    inside = QPoint(tray.left - 1, tray.top + tray.height // 2)
    for screen in QGuiApplication.screens():
        logical = screen.geometry()
        if QRect(logical.topLeft(), logical.size() * screen.devicePixelRatio()).contains(inside):
            return screen
    return QGuiApplication.primaryScreen()


@dataclass(frozen=True)
class _Style:
    frame: str
    text: str
    light: bool  # the chips sit on a light background

    @staticmethod
    def of(settings: HudSettings, *, light: bool) -> _Style:
        """Native: transparent on the taskbar, following its theme. Box: a dark box."""
        if settings.look == "box":
            return _Style(theme.HUD_BOX, theme.TEXT, light=False)
        text = theme.HUD_TEXT_LIGHT if light else theme.TEXT
        return _Style("background: transparent;", text, light)


def _active_title(active: Task | Idle) -> str:
    """The title, or for a task with steps the step it's on ("rerun CI · 2/4"): the HUD has
    little room, and the step is what to do now."""
    match active:
        case Task() as task:
            return step_line(task) or task.title
        case Idle():
            return ""


def _active(title: str, style: _Style, room: int) -> QWidget:
    """An orange dot, like the Active card's border, then the title."""
    name = _text("", style.text, 13)
    shortened = name.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, room)
    name.setText(shortened)
    name.setToolTip(title if shortened != title else "")
    return _beside(_text("●", theme.ORANGE, 11), name)


def _chips(shown: Shown, settings: HudSettings, style: _Style, *, calm: bool) -> list[QWidget]:
    """Messages waiting for me, then the counts. Never an empty box: with nothing active, no
    messages and every count zero, a tick says glance is here, and all is calm."""
    if calm and not shown.inbox and all(count.value == 0 for count in shown.counts):
        return [_all_clear()]
    waiting = [_waiting(shown.inbox, style)] if shown.inbox else []
    return [*waiting, *(_count(count, settings, style) for count in shown.counts)]


def _waiting(inbox: tuple[Message, ...], style: _Style) -> QWidget:
    """A chip tinted yellow: a dot, who the top message is from, and +2 for two more."""
    fill, ink = _tinted(theme.YELLOW, light=style.light, darker=240)  # yellow is light: deeper
    sender, count = inbox[0].sender, len(inbox)
    more = [_text(f"+{count - 1}", ink, 13, QFont.Weight.Bold)] if count > 1 else []
    dot = _text("●", ink, 13, QFont.Weight.Bold)
    tip = f"{count} waiting · open glance to read"
    return _chip(fill, tip, dot, _text(sender, ink, 13), *more)


def _all_clear() -> QWidget:
    """A green tick, like v1's "all clear", when nothing is active and every count is zero."""
    tick = _text("✓", theme.GREEN, 20, QFont.Weight.Bold)
    tick.setToolTip("all clear")
    return tick


def _count(count: Count, settings: HudSettings, style: _Style) -> QWidget:
    """A chip: the entry's icon (or label) and number, tinted in its source's colour while it's
    calm, so the HUD is never grey on grey; solid amber when it's high, red when it's very high.
    A count of -1 means its provider failed: a red "!"."""
    failed = count.value < 0
    level = 3 if failed else count.level
    if level >= 2:
        fill, ink = (theme.HUD_HIGH if level == 2 else theme.HUD_ALERT), theme.BRIGHT
    else:
        fill, ink = _tinted(theme.HUD_SOURCES.get(count.icon, theme.BLUE), light=style.light)
    number = _text("!" if failed else str(count.value), ink, 13, QFont.Weight.Bold)
    tip = f"{count.label}: {'failed' if failed else count.value}"
    return _chip(fill, tip, _symbol(count, settings, ink), number)


def _tinted(colour: str, *, light: bool, darker: int = 180) -> tuple[str, str]:
    """A calm chip's fill, its colour see-through, and its ink: 5:1 or more on either taskbar."""
    source = QColor(colour)
    source.setAlpha(theme.HUD_TINT[light])
    fill = source.name(QColor.NameFormat.HexArgb)
    source.setAlpha(255)
    return fill, (source.darker(darker) if light else source.lighter(125)).name()


def _chip(fill: str, tip: str, *inside: QWidget) -> QFrame:
    chip = QFrame()
    chip.setObjectName("chip")  # so the style is the chip's, not its contents'
    chip.setStyleSheet(f"QFrame#chip {{ background: {fill}; border-radius: 8px; }}")
    chip.setToolTip(tip)
    row = QHBoxLayout(chip)
    row.setContentsMargins(7, 3, 9, 3)
    row.setSpacing(5)
    for widget in inside:
        row.addWidget(widget)
    return chip


def _symbol(count: Count, settings: HudSettings, colour: str) -> QLabel:
    """Its label, or an outline icon if the entry names one in icons.HUD, else its icon text."""
    if settings.labels == "text":
        return _text(count.label, colour, 13)
    if count.icon not in icons.HUD:
        return _text(count.icon, colour, 13)  # the number's size, so every chip is as tall
    symbol = QLabel()
    symbol.setPixmap(icons.pixmap(icons.HUD[count.icon], colour, 16))
    return symbol


def _text(text: str, colour: str, size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QLabel:
    shown = theme.label(text, "dim", size, weight)
    shown.setStyleSheet(f"color: {colour};")
    return shown


def _beside(*widgets: QWidget) -> QWidget:
    cell = QWidget()
    row = QHBoxLayout(cell)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    for widget in widgets:
        row.addWidget(widget)
    return cell
