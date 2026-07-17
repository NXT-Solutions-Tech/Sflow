"""Lucide SVG icon helper — offline, theme-aware, cached.

Loads a vendored Lucide SVG (``assets/icons/*.svg``), recolors its
``currentColor`` stroke to a token color, and renders a crisp ``QIcon``/
``QPixmap`` at the requested size. Replaces the emoji-as-text glyphs the UI
used to rely on.

Usage:
    from ui import icons
    btn.setIcon(icons.icon("home", size=18))                 # theme text color
    btn.setIcon(icons.icon("settings", color=theme.C.ACCENT))
"""
from __future__ import annotations

import os

from PyQt6.QtCore import QByteArray, QRectF, Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer

from ui import theme


# Friendly name -> vendored Lucide file (without .svg). Keeps call sites stable
# even if we swap the underlying Lucide glyph.
LUCIDE = {
    "home": "house",
    "insights": "chart-column-big",
    "bar-chart": "chart-column-big",
    "history": "history",
    "clock": "history",
    "dictionary": "book-open",
    "book-open": "book-open",
    "snippets": "sparkles",
    "sparkles": "sparkles",
    "transforms": "wand-sparkles",
    "wand": "wand-sparkles",
    "settings": "settings",
    "more": "ellipsis-vertical",
    "more-vertical": "ellipsis-vertical",
    "search": "search",
    "refresh": "refresh-cw",
    "refresh-cw": "refresh-cw",
    "x": "x",
    "close": "x",
    "command": "command",
    "keyboard": "keyboard",
    "check": "check",
    "sun": "sun",
    "moon": "moon",
    "trash": "trash-2",
    "copy": "copy",
    "edit": "pencil",
    "pencil": "pencil",
    "retry": "rotate-ccw",
    "plus": "plus",
    "mic": "mic",
    "shield": "shield-check",
    "shield-check": "shield-check",
    "key": "key-round",
}

_SVG_CACHE: dict[str, str] = {}
_PIX_CACHE: dict[tuple, QPixmap] = {}


def _svg_text(name: str) -> str | None:
    fname = LUCIDE.get(name, name)
    if fname in _SVG_CACHE:
        return _SVG_CACHE[fname]
    path = os.path.join(theme.ICONS_DIR, f"{fname}.svg")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    _SVG_CACHE[fname] = txt
    return txt


def pixmap(name: str, color: str | None = None, size: int = 18) -> QPixmap:
    """Render a recolored Lucide glyph to a crisp (2x) QPixmap."""
    if color is None:
        color = theme.C.TEXT_DIM
    key = (LUCIDE.get(name, name), color, size)
    cached = _PIX_CACHE.get(key)
    if cached is not None:
        return cached

    txt = _svg_text(name)
    if txt is None:
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        _PIX_CACHE[key] = pm
        return pm

    txt = txt.replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(txt.encode("utf-8")))

    scale = 2  # render at 2x for retina crispness
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(p, QRectF(0, 0, size * scale, size * scale))
    p.end()
    pm.setDevicePixelRatio(float(scale))
    _PIX_CACHE[key] = pm
    return pm


def icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    """Return a QIcon for the named Lucide glyph, recolored to ``color``
    (defaults to the active theme's secondary text token)."""
    return QIcon(pixmap(name, color=color, size=size))


def clear_cache() -> None:
    """Drop cached pixmaps — call after a theme change so icons re-tint."""
    _PIX_CACHE.clear()
