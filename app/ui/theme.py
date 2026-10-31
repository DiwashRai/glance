"""Board F's look: colours, the font, a plain label in it, and one stylesheet for every part of
the overlay.

Widgets pick their style with a `role` property (`role="card"`), since Qt stylesheets match
properties rather than CSS classes.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QWidget

CARD = "#151517"
BORDER = "#2a2a2d"
ACTIVE_CARD = "#1a150e"
PROMPT = "#1b1b1e"
PROMPT_EDGE = "#45454a"
DASHED_EDGE = "#3a3a3d"
TEXT = "#e5e5e5"
BRIGHT = "#ffffff"
DIM = "#8a8a8a"
NUMBER = "#6b6b70"
KEY = "#b5b5b8"
SELECTION = "#3a2810"
ORANGE = "#f39c12"
YELLOW = "#f4d03f"
YELLOW_GLOW = "#40f4d03f"  # the yellow, faint: a ring round the HUD's dot
BLUE = "#5dade2"
RED = "#e74c3c"
BACKDROP_DIM = 0.6  # how dark the screen behind the overlay goes, 0 to 1

# The HUD on the taskbar in a light theme (canvas board W9, E). The dark one (C) is the overlay's
HUD_LIGHT_BOX = "#ffffff"
HUD_LIGHT_EDGE = "#d4d4d8"
HUD_LIGHT_ICON = "#4a4a4f"
HUD_LIGHT_TEXT = "#1b1b1d"
HUD_LIGHT_ORANGE = "#e8700a"
HUD_LIGHT_RED = "#c0392b"
BADGE_RED = HUD_LIGHT_RED  # a tray-native badge, on either taskbar: deep enough for white on it
HUD_LIGHT_YELLOW = "#f1c40f"  # the dot
HUD_LIGHT_RING = "#8a6d00"  # dark gold round the dot, so it shows on white

FONTS = ["JetBrains Mono", "JetBrainsMono NF", "Cascadia Mono", "Consolas"]


def font(size: int, weight: QFont.Weight = QFont.Weight.Normal, spacing: float = 0) -> QFont:
    chosen = QFont()
    chosen.setFamilies(FONTS)
    chosen.setPixelSize(size)
    chosen.setWeight(weight)
    chosen.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return chosen


def styled[W: QWidget](widget: W, role: str) -> W:
    widget.setProperty("role", role)
    return widget


def label(
    text: str, role: str, size: int = 13, weight: QFont.Weight = QFont.Weight.Normal
) -> QLabel:
    """Always plain text, never HTML."""
    widget = styled(QLabel(text), role)
    widget.setFont(font(size, weight))
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def restyle(widget: QWidget, name: str, value: str) -> None:
    """Change a style property and make Qt apply the stylesheet to it again."""
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


STYLESHEET = f"""
QWidget {{ color: {TEXT}; }}
/* almost invisible, not clear, so a click between the cards stays with the overlay. The alpha is
   out of 255: Qt reads 1 or less as a fraction, so rgba(0, 0, 0, 1) would be solid black */
QFrame[role="panel"] {{ background: rgba(0, 0, 0, 2); border: none; }}
QFrame[role="card"] {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; }}
QFrame[role="active"] {{
    background: {ACTIVE_CARD}; border: 1px solid {ORANGE}; border-radius: 14px;
}}
QFrame[role="idle"] {{
    background: transparent; border: 1px dashed {DASHED_EDGE}; border-radius: 14px;
}}
QFrame[role="prompt"] {{
    background: {PROMPT}; border: 1px solid {PROMPT_EDGE}; border-radius: 14px;
}}
QFrame[role="inbox"] {{ background: {CARD}; border: 1px solid {YELLOW}; border-radius: 14px; }}
QLabel {{ background: transparent; border: none; }}
QLabel[role="header"] {{ color: {DIM}; }}
QLabel[role="active-header"] {{ color: {ORANGE}; }}
QLabel[role="inbox-header"] {{ color: {YELLOW}; }}
QLabel[role="title"] {{ color: {BRIGHT}; }}
QLabel[role="dim"] {{ color: {DIM}; }}
QLabel[role="number"] {{ color: {NUMBER}; }}
QLabel[role="kbd"] {{
    color: {KEY}; border: 1px solid {DASHED_EDGE}; border-bottom-width: 2px; border-radius: 5px;
    padding: 0px 6px;
}}
QLabel[role="prompt-mark"] {{ color: {BLUE}; }}
QLabel[tone="agent"] {{ color: {YELLOW}; }}
QPlainTextEdit {{
    background: transparent; border: none; color: {BRIGHT}; selection-background-color: {SELECTION};
}}
QLabel[tone="done"] {{ color: {TEXT}; }}
QLabel[tone="refused"] {{ color: {ORANGE}; }}
QLabel[tone="error"] {{ color: {RED}; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 8px; }}
QMenu {{ background: {CARD}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ color: {TEXT}; padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {SELECTION}; color: {BRIGHT}; }}
"""
