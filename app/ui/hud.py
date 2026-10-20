"""The HUD: a row on every taskbar, just left of the tray on the main one and of the clock on the
others, in one of board W9's looks, picked from the menu:
- **box:** a box, dark (C) or light (E), each count its icon then its number;
- **tray-native:** drawn straight onto the taskbar (A, B), each count its icon with the number
  in a badge on its corner.
Light or dark is picked from the menu too, or follows the taskbar. A number is plain while calm,
orange when high and red when very high; a count of 0 shows its icon alone. While messages for
me are waiting, a yellow dot goes first, on the side towards the middle of the screen.

Every 2 seconds, and when a monitor comes or goes, it finds the taskbars showing, sits on each
and lifts itself back above them. One hides with its taskbar (a full-screen video or game on
that monitor, or auto-hide). It only redraws when what it shows has changed. A click on any of
them opens the overlay; a right-click shows the tray icon's menu.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QMouseEvent, QPainter, QScreen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QWidget

from app.core.model import HudSettings, Message
from app.counts import Count, CountsFile
from app.ui import icons, theme
from app.win32.taskbar import Tray, find_taskbars, lift, light_taskbar

TICK_MS = 2000
GAP = 8  # between the HUD and the tray, in Qt pixels
HEIGHT_SHARE = 0.72  # of the taskbar's height
SIZE = 17  # the numbers' text, in Qt pixels; the icons are a little bigger
BADGE = 12  # a tray-native badge's text


@dataclass(frozen=True)
class Shown:
    """What the HUD is showing, so it only redraws when this changes."""

    counts: tuple[Count, ...]
    light: bool
    inbox: tuple[Message, ...] = ()
    native: bool = False  # the tray-native look, not the box


class Hud:
    """A bar on each taskbar, all showing the same. A bar is made when a taskbar first appears,
    and hides with it."""

    def __init__(
        self,
        settings: HudSettings,
        inbox: Callable[[], tuple[Message, ...]],
        counts_file: Path,
        clicked: Callable[[], None],
        menu: QMenu,
    ) -> None:
        self.settings = settings
        self.inbox = inbox
        self.counts = CountsFile(counts_file)
        self.clicked = clicked
        self.menu = menu
        # Picked from the menu: theme "system", "light" or "dark"; look "box" or "native"
        self.picked = {"theme": "system", "look": "box"}
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
            self.bars.append(_Bar(self.settings, self.clicked, self.menu))
        showing = [(bar, tray) for bar, tray in zip(self.bars, trays, strict=False) if tray.showing]
        for bar in set(self.bars) - {bar for bar, _ in showing}:
            bar.hide()
        if showing:
            # Drawn straight onto the taskbar, the native look always matches it: the theme picked
            # is the box's
            chosen = self.picked["theme"]
            native = self.picked["look"] == "native"
            light = light_taskbar() if native or chosen == "system" else chosen == "light"
            shown = Shown(self.counts.read(), light, self.inbox(), native)
            for bar, tray in showing:
                bar.show_on(tray, shown)


class _Bar(QWidget):
    """The HUD on one taskbar."""

    def __init__(self, settings: HudSettings, clicked: Callable[[], None], menu: QMenu) -> None:
        super().__init__()
        self.settings = settings
        self.clicked = clicked
        self.menu = menu
        self.shown = Shown((), light=False)
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
        self.row.setSpacing(12)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.frame)
        self.items: list[QWidget] = []

    def show_on(self, tray: Tray, shown: Shown) -> None:
        if not self.items or shown != self.shown:  # drawn at least once, even if it's as it began
            self.shown = shown
            self._draw(shown)
        self._place(tray, _screen(tray))
        self.show()
        lift(int(self.winId()))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked()
        elif event.button() == Qt.MouseButton.RightButton:
            self.menu.popup(event.globalPosition().toPoint())

    def _draw(self, shown: Shown) -> None:
        for item in self.items:
            self.row.removeWidget(item)
            item.hide()
            item.deleteLater()
        style = LIGHT if shown.light else DARK
        box = f"background: {style.box}; border: 1px solid {style.edge}; border-radius: 8px;"
        native = "background: transparent; border: none;"
        self.frame.setStyleSheet(f"QFrame#hud {{ {native if shown.native else box} }}")
        self.items = _items(shown, self.settings, style)
        for item in self.items:
            self.row.addWidget(item, alignment=Qt.AlignmentFlag.AlignVCenter)  # its own height
            item.show()  # now, so its width counts when the HUD is measured and placed

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
    box: str
    edge: str
    icon: str  # in the box
    text: str  # a calm number in the box
    high: str
    alert: str
    tray: str  # icons drawn straight onto the taskbar
    badge: str  # a calm badge, with `badge_ink` on it
    badge_ink: str
    dot: str
    ring: str  # around the dot, so it stands out on either


DARK = _Style(
    theme.CARD,
    theme.BORDER,
    theme.KEY,
    theme.TEXT,
    theme.ORANGE,
    theme.RED,
    "#d4d4d8",
    "#3a3a3f",
    theme.BRIGHT,
    theme.YELLOW,
    theme.YELLOW_GLOW,
)
LIGHT = _Style(
    theme.HUD_LIGHT_BOX,
    theme.HUD_LIGHT_EDGE,
    theme.HUD_LIGHT_ICON,
    theme.HUD_LIGHT_TEXT,
    theme.HUD_LIGHT_ORANGE,
    theme.HUD_LIGHT_RED,
    "#1f1f22",
    "#cfcfd4",
    "#111113",
    theme.HUD_LIGHT_YELLOW,
    theme.HUD_LIGHT_RING,
)


def _items(shown: Shown, settings: HudSettings, style: _Style) -> list[QWidget]:
    """Never empty: with no messages and no counts (no collector yet), a tick says glance is
    here."""
    if not shown.inbox and not shown.counts:
        return [_no_counts(style, shown.native)]
    dot = [_dot(shown.inbox, style)] if shown.inbox else []
    draw = _badged if shown.native else _boxed
    return [*dot, *(draw(count, settings, style) for count in shown.counts)]


def _dot(inbox: tuple[Message, ...], style: _Style) -> QLabel:
    """Messages for me are waiting: who from is in its tooltip."""
    drawn = icons.blank(12)
    painter = QPainter(drawn)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    for colour, inset in ((style.ring, 0.5), (style.dot, 2.0)):
        painter.setBrush(QColor(colour))
        painter.drawEllipse(QRectF(inset, inset, 12 - 2 * inset, 12 - 2 * inset))
    painter.end()
    dot = QLabel()
    dot.setPixmap(drawn)
    dot.setFixedSize(20, 20)  # room around it, so its tooltip is easy to hover
    dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sender, count = inbox[0].sender, len(inbox)
    more = f", and {count - 1} more" if count > 1 else ""
    dot.setToolTip(f"a message from {sender}{more} · open glance to read")
    return dot


def _no_counts(style: _Style, native: bool) -> QWidget:
    """A grey tick: glance is here, with nothing to count yet."""
    tick = _text("✓", style.tray if native else style.icon, SIZE + 5, QFont.Weight.Bold)
    tick.setToolTip("no counts yet")
    return tick


def _number(count: Count) -> str:
    """ "" for 0, so only the icon shows; "!" for a provider that failed (-1)."""
    return {0: "", -1: "!"}.get(count.value, str(count.value))


def _level(count: Count) -> int:
    """0 calm, 1 high, 2 very high (or failed): the collector's top two levels get colour."""
    return 2 if count.value < 0 else max(count.level - 1, 0)


def _boxed(count: Count, settings: HudSettings, style: _Style) -> QWidget:
    """Its icon or label, then its number: plain, orange when high, red when very high."""
    colour = (style.text, style.high, style.alert)[_level(count)]
    number = _text(_number(count), colour, SIZE, QFont.Weight.Bold)
    cell = _beside(_symbol(count, settings, style.icon), number)
    number.setVisible(count.value != 0)
    cell.setToolTip(_tip(count))
    return cell


def _badged(count: Count, settings: HudSettings, style: _Style) -> QWidget:
    """Its icon in the taskbar's colour, with its number in a badge on the bottom-right corner:
    grey, orange when high, red when very high."""
    level = _level(count)
    fill = (style.badge, theme.ORANGE, theme.BADGE_RED)[level]
    ink = (style.badge_ink, "#1a1206", theme.BRIGHT)[level]
    cell = QWidget()
    symbol = _symbol(count, settings, style.tray)
    symbol.setParent(cell)
    symbol.adjustSize()
    cell.setToolTip(_tip(count))
    if count.value == 0:  # as tall as one with a badge, so the icons line up
        cell.setFixedSize(symbol.width(), symbol.height() + 8)
        return cell
    badge = _text(_number(count), ink, BADGE, QFont.Weight.Bold)
    badge.setParent(cell)
    badge.setStyleSheet(f"color: {ink}; background: {fill}; border-radius: 8px; padding: 0 4px;")
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setFixedHeight(17)
    badge.setMinimumWidth(17)
    badge.adjustSize()
    # On an icon's corner; after a text label, so it doesn't cover the last letter
    left = symbol.width() + (2 if settings.labels == "text" else -7)
    top = symbol.height() - 9
    badge.move(left, top)
    cell.setFixedSize(left + badge.width(), top + badge.height())
    return cell


def _tip(count: Count) -> str:
    said = {0: "none", -1: "failed"}.get(count.value, str(count.value))
    return f"{count.label}: {said}"


def _symbol(count: Count, settings: HudSettings, colour: str) -> QLabel:
    """Its label, or an outline icon if the entry names one in icons.HUD, else its icon text."""
    if settings.labels == "text":
        return _text(count.label, colour, SIZE, QFont.Weight.DemiBold)
    if count.icon not in icons.HUD:
        return _text(count.icon, colour, SIZE)  # the number's size, so every count is as tall
    symbol = QLabel()
    symbol.setPixmap(icons.pixmap(icons.HUD[count.icon], colour, SIZE + 2))
    return symbol


def _text(text: str, colour: str, size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QLabel:
    shown = theme.label(text, "dim", size, weight)
    shown.setStyleSheet(f"color: {colour};")
    return shown


def _beside(*widgets: QWidget) -> QWidget:
    cell = QWidget()
    row = QHBoxLayout(cell)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(5)
    for widget in widgets:
        row.addWidget(widget)
    return cell
