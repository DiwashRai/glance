"""The overlay window, the HUD on the taskbar, the tray icon and Ctrl+Space, wired together. The
inbox folder is watched, so a message shows on the HUD as soon as it comes."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QFileSystemWatcher, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from app.controller import Controller
from app.core.model import HudSettings
from app.ui.hud import Hud
from app.ui.window import Window
from app.win32.hotkey import Hotkey


class Shell:
    def __init__(
        self, app: QApplication, controller: Controller, hud: HudSettings, counts_file: Path
    ) -> None:
        self.controller = controller
        self.window = Window(controller)
        self.hud = Hud(
            hud, controller.saved, lambda: controller.inbox, counts_file, self.window.open
        )
        controller.read_inbox()  # which creates the folder, to watch
        self.watcher = QFileSystemWatcher([str(controller.store.inbox_path)])
        self.watcher.directoryChanged.connect(self._inbox_changed)
        self.hotkey = Hotkey(self.window.pressed)
        self.tray = _tray(self.window)
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


def _tray(window: Window) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(_icon(), window)
    tray.setToolTip("glance · Ctrl+Space")
    menu = QMenu(window)
    open_action = QAction("Open  (Ctrl+Space)", menu)
    open_action.triggered.connect(window.open)
    quit_action = QAction("Quit glance", menu)
    quit_action.triggered.connect(QCoreApplication.quit)
    menu.addActions([open_action, quit_action])
    tray.setContextMenu(menu)
    return tray


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
