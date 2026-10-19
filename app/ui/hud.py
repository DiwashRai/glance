"""The HUD: one row on the taskbar, just left of the tray. The active task (optional), then each
count from the collector as a chip: its icon or label and its number, coloured by its source and
its level.

Every 2 seconds it hides while a full-screen app is in front, otherwise finds the tray, sits next
to it and lifts itself back above the taskbar. It only redraws when what it shows has changed.
Clicking it opens the overlay.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QMouseEvent
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
        self.row.setContentsMargins(10, 0, 10, 0)
        self.row.setSpacing(8)
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
            self.row.addWidget(item, alignment=Qt.AlignmentFlag.AlignVCenter)  # its own height
            item.show()  # now, so its width counts when the HUD is measured and placed
        used = sum(item.sizeHint().width() + self.row.spacing() for item in self.items)
        room = min(ACTIVE_WIDTH, shown.room - used)
        if active and room >= MIN_ACTIVE_WIDTH:
            self.items.insert(0, _active(active, style, room))
            self.row.insertWidget(0, self.items[0], alignment=Qt.AlignmentFlag.AlignVCenter)
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
    source = QColor(theme.HUD_SOURCES.get(count.icon, theme.BLUE))
    if level >= 2:
        fill, ink = (theme.HUD_HIGH if level == 2 else theme.HUD_ALERT), theme.BRIGHT
    else:
        source.setAlpha(theme.HUD_TINT[style.light])
        fill = source.name(QColor.NameFormat.HexArgb)
        source.setAlpha(255)
        ink = (source.darker(180) if style.light else source.lighter(125)).name()  # 5:1 or more
    chip = QFrame()
    chip.setObjectName("chip")  # so the style is the chip's, not its contents'
    chip.setStyleSheet(f"QFrame#chip {{ background: {fill}; border-radius: 8px; }}")
    chip.setToolTip(f"{count.label}: {'failed' if failed else count.value}")
    inside = QHBoxLayout(chip)
    inside.setContentsMargins(7, 3, 9, 3)
    inside.setSpacing(5)
    inside.addWidget(_symbol(count, settings, ink))
    inside.addWidget(_text("!" if failed else str(count.value), ink, 13, QFont.Weight.Bold))
    return chip


def _symbol(count: Count, settings: HudSettings, colour: str) -> QLabel:
    """Its label, or an outline icon if the entry names one in icons.HUD, else its icon text."""
    if settings.labels == "text":
        return _text(count.label, colour, 13)
    if count.icon not in icons.HUD:
        return _text(count.icon, colour, 15)
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
