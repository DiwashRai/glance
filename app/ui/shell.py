"""The overlay window, the HUD on the taskbar, the tray icon and Ctrl+Space, wired together. The
inbox folder is watched, so a message shows on the HUD as soon as it comes. The HUD's theme and
look are picked from the menu (the tray icon's, or the HUD's on a right-click) and kept for next
time."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QFileSystemWatcher, QSettings, Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from app.controller import Controller
from app.core.model import HudSettings
from app.ui.hud import Hud
from app.ui.window import Window
from app.win32.hotkey import Hotkey

# The HUD's choices in the menu: each setting, its title, then its options, the default first
CHOICES = (
    # The box's theme: the tray-native look always matches the taskbar
    ("theme", "HUD theme", (("system", "System default"), ("light", "Light"), ("dark", "Dark"))),
    ("look", "HUD look", (("box", "Box"), ("native", "Tray-native"))),
)


class Shell:
    def __init__(
        self, app: QApplication, controller: Controller, hud: HudSettings, counts_file: Path
    ) -> None:
        self.controller = controller
        self.window = Window(controller)
        self.kept = QSettings("glance", "glance")  # what's picked from the menu, in the registry
        picked = {key: self._kept(key, options) for key, _, options in CHOICES}
        menu = _menu(self.window, picked, self._picked)
        self.hud = Hud(hud, lambda: controller.inbox, counts_file, self.window.open, menu)
        self.hud.picked = picked
        controller.read_inbox()  # which creates the folder, to watch
        self.watcher = QFileSystemWatcher([str(controller.store.inbox_path)])
        self.watcher.directoryChanged.connect(self._inbox_changed)
        self.hotkey = Hotkey(self.window.pressed)
        self.tray = _tray(self.window, menu)
        self.tray.activated.connect(self._tray_clicked)
        app.installNativeEventFilter(self.hotkey)
        app.aboutToQuit.connect(self.hotkey.unregister)
        app.screenAdded.connect(self.hud.tick)  # a monitor comes or goes: a bar for each taskbar
        app.screenRemoved.connect(self.hud.tick)
        app.setQuitOnLastWindowClosed(False)  # it lives in the tray; Ctrl+Space opens it

    def start(self) -> None:
        """Registers Ctrl+Space (raising if another app has it), then shows the tray icon and the
        HUD."""
        self.hotkey.register()
        self.tray.show()
        self.hud.start()

    def _tray_clicked(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """A left click opens it. Clicking the tray takes the focus first, which hides an open
        window, so a click always opens rather than toggling. A right-click only shows the menu."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.window.open()

    def _inbox_changed(self, _folder: str) -> None:
        """A message came, or one was cleared: the HUD, and the overlay if it's open, show it."""
        self.controller.read_inbox()
        self.hud.tick()
        self.window.show_inbox()

    def _kept(self, key: str, options: tuple[tuple[str, str], ...]) -> str:
        """As last picked, or the default: also for a registry edited by hand."""
        kept = str(self.kept.value(f"hud/{key}", ""))
        return kept if kept in dict(options) else options[0][0]

    def _picked(self, action: QAction) -> None:
        key, value = str(action.data()).split("=")
        self.hud.picked[key] = value
        self.kept.setValue(f"hud/{key}", value)
        self.hud.tick()


def _tray(window: Window, menu: QMenu) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(_icon(), window)
    tray.setToolTip("glance · Ctrl+Space")
    tray.setContextMenu(menu)
    return tray


def _menu(window: Window, picked: dict[str, str], chose: Callable[[QAction], None]) -> QMenu:
    """Open, the HUD's choices (the ones in use ticked), and quit."""
    menu = QMenu(window)
    menu.addAction("Open  (Ctrl+Space)").triggered.connect(window.open)
    for key, title, options in CHOICES:
        submenu = menu.addMenu(title)
        group = QActionGroup(submenu)  # one ticked at a time
        for value, name in options:
            action = submenu.addAction(name)
            action.setData(f"{key}={value}")
            action.setCheckable(True)
            action.setChecked(value == picked[key])
            group.addAction(action)
        group.triggered.connect(chose)
    menu.addSeparator()
    menu.addAction("Quit glance").triggered.connect(QCoreApplication.quit)
    return menu


def _icon() -> QIcon:
    """An orange dot, like the Active card's border."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#f39c12"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, 24, 24)
    painter.end()
    return QIcon(pixmap)
