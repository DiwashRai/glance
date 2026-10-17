"""The HUD: one row on the taskbar, just left of the tray. The active task (optional), then each
count from the collector, as its icon or its label plus a number coloured by level.

Every 2 seconds it hides while a full-screen app is in front, otherwise finds the tray, sits next
to it and lifts itself back above the taskbar. It only redraws when what it shows has changed.
Clicking it opens the overlay.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication, QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from app.core.model import HudSettings, Idle, Lists, Task, step_line, working
from app.counts import Count, CountsFile
from app.ui import icons, theme
from app.win32.taskbar import NoTaskbar, Tray, find_tray, full_screen_app, lift, light_taskbar

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
    room: int  # the most the HUD may take, in Qt pixels


class Hud(QWidget):
    def __init__(
        self,
        settings: HudSettings,
        lists: Callable[[], Lists],
        counts_file: Path,
        clicked: Callable[[], None],
    ) -> None:
        super().__init__()
        self.settings = settings
        self.lists = lists
        self.counts = CountsFile(counts_file)
        self.clicked = clicked
        self.shown = Shown("", (), light=False, room=0)
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
        self.row.setContentsMargins(10, 0, 10, 0)  # the full height for the badged icons
        self.row.setSpacing(16)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.frame)
        self.items: list[QWidget] = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def start(self) -> None:
        """The first check runs once the app is running, so a problem in it (a bad counts file,
        say) is shown in the overlay instead of stopping glance from starting."""
        QTimer.singleShot(0, self.tick)
        self.timer.start(TICK_MS)

    def tick(self) -> None:
        if full_screen_app():
            self.hide()
            return
        match find_tray():
            case NoTaskbar():
                self.hide()
            case Tray() as tray:
                scale = QGuiApplication.primaryScreen().devicePixelRatio()
                self._redraw_if_changed(room=int(tray.width / scale * MAX_SHARE))
                self._place(tray, scale)
                self.show()
                lift(int(self.winId()))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked()

    def _redraw_if_changed(self, room: int) -> None:
        active = _active_title(working(self.lists().active))
        shown = Shown(active, self.counts.read(), light_taskbar(), room)
        if shown != self.shown:
            self.shown = shown
            self._draw(shown)

    def _draw(self, shown: Shown) -> None:
        """The counts go in first. The active task then goes in front of them, shortened to the
        room they leave, or left out if there's too little."""
        for item in self.items:
            self.row.removeWidget(item)
            item.hide()
            item.deleteLater()
        style = _Style.of(self.settings, light=shown.light)
        self.frame.setStyleSheet(f"QFrame#hud {{ {style.frame} }}")
        active = shown.active if self.settings.show_active else ""
        if not active and all(count.value == 0 for count in shown.counts):
            self.items = [_all_clear()]  # never an empty box: glance is here, and all is calm
        else:
            self.items = [_count(count, self.settings, style) for count in shown.counts]
        for item in self.items:
            self.row.addWidget(item)
            item.show()  # now, so its width counts when the HUD is measured and placed
        used = sum(item.sizeHint().width() + self.row.spacing() for item in self.items)
        room = min(ACTIVE_WIDTH, shown.room - used)
        if active and room >= MIN_ACTIVE_WIDTH:
            self.items.insert(0, _active(active, style, room))
            self.row.insertWidget(0, self.items[0])
            self.items[0].show()

    def _place(self, tray: Tray, scale: float) -> None:
        """Tray rectangles are in real pixels; the main taskbar is on the primary screen."""
        height = int(tray.height / scale * HEIGHT_SHARE)
        self.setFixedHeight(height)
        self.adjustSize()
        x = int(tray.left / scale) - self.width() - GAP
        y = int((tray.top + tray.height / 2) / scale - height / 2)
        self.move(x, y)


@dataclass(frozen=True)
class _Style:
    frame: str
    text: str
    levels: tuple[str, ...]  # the number's stylesheet at levels 0 to 3
    badged: bool  # numbers sit on their icon's corner, like a notification badge

    @staticmethod
    def of(settings: HudSettings, *, light: bool) -> _Style:
        """Native: transparent on the taskbar, following its theme, with each count as a badge on
        its icon, rimmed in the taskbar's colour. Box: a dark box, with coloured numbers."""
        if settings.look == "box":
            plain = f"color: {theme.TEXT};"
            levels = (plain, plain, f"color: {theme.ORANGE};", f"color: {theme.RED};")
            return _Style(theme.HUD_BOX, theme.TEXT, levels, badged=False)
        text = theme.HUD_TEXT_LIGHT if light else theme.TEXT
        quiet = f"background: {theme.HUD_QUIET_LIGHT if light else theme.HUD_QUIET_DARK};"
        rim = theme.HUD_RIM_LIGHT if light else theme.HUD_RIM_DARK
        badge = (
            f" color: {theme.BRIGHT}; border: 2px solid {rim}; border-radius: 7px; padding: 0 4px;"
        )
        levels = tuple(fill + badge for fill in (quiet, quiet, theme.HUD_WARN, theme.HUD_ALERT))
        return _Style("background: transparent;", text, levels, badged=True)


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
    dot = theme.label("●", "dim", 11)
    dot.setStyleSheet(f"color: {theme.ORANGE};")
    name = theme.label("", "title", 13)
    name.setStyleSheet(f"color: {style.text};")
    shortened = name.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, room)
    name.setText(shortened)
    name.setToolTip(title if shortened != title else "")
    return _beside(dot, name)


def _all_clear() -> QWidget:
    """A green tick, like v1's "all clear", when nothing is active and every count is zero."""
    tick = theme.label("✓", "dim", 20, QFont.Weight.Bold)
    tick.setStyleSheet(f"color: {theme.GREEN};")
    tick.setToolTip("all clear")
    return tick


def _count(count: Count, settings: HudSettings, style: _Style) -> QWidget:
    """The entry's icon or label, with its number. A count of -1 means its provider failed,
    shown as a red "!"."""
    failed = count.value < 0
    weight = QFont.Weight.Bold if style.badged else QFont.Weight.Normal
    number = theme.label(
        "!" if failed else str(count.value), "dim", 11 if style.badged else 13, weight
    )
    number.setStyleSheet(style.levels[3 if failed else count.level])
    number.setToolTip(f"{count.label}: {'failed' if failed else count.value}")
    if settings.labels == "text":
        name = theme.label(count.label, "dim", 13)
        name.setStyleSheet(f"color: {style.text};")
        return _beside(name, number)
    symbol = _symbol(count.icon, style.text)
    return _badged(symbol, number) if style.badged else _beside(symbol, number)


def _symbol(icon: str, colour: str) -> QLabel:
    """An outline icon if the entry names one in icons.HUD, else its text."""
    if icon in icons.HUD:
        symbol = QLabel()
        symbol.setPixmap(icons.pixmap(icons.HUD[icon], colour, 20))
        return symbol
    symbol = theme.label(icon, "dim", 17)
    symbol.setStyleSheet(f"color: {colour};")
    return symbol


def _beside(*widgets: QWidget) -> QWidget:
    cell = QWidget()
    row = QHBoxLayout(cell)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    for widget in widgets:
        row.addWidget(widget)
    return cell


def _badged(symbol: QLabel, number: QLabel) -> QWidget:
    """The number on the icon's bottom-right corner. Placed by hand: a layout can't overlap."""
    cell = QWidget()
    cell.setToolTip(number.toolTip())
    for child in (symbol, number):  # the number last, so it's drawn on top
        child.setParent(cell)
        child.adjustSize()
    number.setMinimumWidth(number.height())  # a single digit is a circle
    number.adjustSize()
    symbol.move(0, 3)
    x = symbol.width() - 7
    y = symbol.y() + symbol.height() - number.height() + 5
    number.move(x, y)
    cell.setFixedSize(x + number.width(), y + number.height())
    return cell
