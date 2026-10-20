"""glance's icons. Each one is a whole SVG, so it can be pasted into a browser or an editor as it
is. They draw in `currentColor`, which `pixmap` swaps for the colour it's given.

The shapes come from the Feather and Lucide icon sets.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

SCALE = 3  # icons are drawn at 3x, so they stay sharp up to 300% display scaling

# The Active card's flame
FLAME = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5'
    " 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5"
    ' 2.5z"/></svg>'
)

# The HUD's counts (canvas board W9). A collector entry picks one by name (`icon = "mail"`); any
# other icon text is shown as it is, such as a Nerd Font glyph.
HUD = {  # a thicker line than the overlay's (2.6, not 2), to read on the taskbar
    "todo": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="9 11 12 14 22 4"/>'
        '<path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>'
    ),
    "mail": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>'
        '<polyline points="22,6 12,13 2,6"/></svg>'
    ),
    "jira": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0'
        ' 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>'
    ),
    "pr": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/>'
        '<path d="M13 6h3a2 2 0 0 1 2 2v7"/><line x1="6" y1="9" x2="6" y2="21"/></svg>'
    ),
}


def pixmap(svg: str, colour: str, size: int) -> QPixmap:
    """One of the icons above, drawn in colour."""
    drawn = blank(size)
    painter = QPainter(drawn)
    coloured = QByteArray(svg.replace("currentColor", colour).encode())
    QSvgRenderer(coloured).render(painter, QRectF(0, 0, size, size))
    painter.end()
    return drawn


def blank(size: int) -> QPixmap:
    """A transparent square, drawn at SCALE times the size so it stays sharp."""
    drawn = QPixmap(size * SCALE, size * SCALE)
    drawn.setDevicePixelRatio(SCALE)
    drawn.fill(Qt.GlobalColor.transparent)
    return drawn
