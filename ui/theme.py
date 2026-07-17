"""SFlow design system — semantic tokens + global QSS for light & dark.

Single source of truth for color, type and radius. Replaces the old dark-only
``class C`` palette that used to live in ``ui/hub_window.py``.

Design language: Wispr Flow — warm cream light (hero) + refined dark complement,
one purple accent (``#8c50dc``, the brand/logo color), Instrument Serif display
titles + Inter UI sans, standardized radii (8 / 12 / full).

The module keeps an *active scheme* (``light`` | ``dark``). Legacy code reads
colors through the live ``C`` proxy (``C.BG``, ``C.ACCENT`` …) which resolves
against whatever scheme is active — so existing inline stylesheets become
theme-aware for free, and the offscreen preview harness can render any surface in
either scheme by flipping ``set_active_scheme`` before construction.
"""
from __future__ import annotations

import os
import sys

from PyQt6.QtGui import QFontDatabase, QGuiApplication
from PyQt6.QtCore import Qt


# ---------- Resource resolution (dev + PyInstaller bundle) ----------
def _resource_dir() -> str:
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # type: ignore[attr-defined]
    # ui/theme.py -> project root
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


RESOURCE_DIR = _resource_dir()
FONTS_DIR = os.path.join(RESOURCE_DIR, "assets", "fonts")
ICONS_DIR = os.path.join(RESOURCE_DIR, "assets", "icons")

# Font family names (as registered by the bundled .ttf files)
SERIF = "Instrument Serif"   # display / section titles
SANS = "Inter"               # body / controls
MONO = "SF Mono"             # code-ish surfaces (dictionary editor) — system

# Radius scale
RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_PILL = 999


# ---------- Semantic tokens ----------
_DARK = {
    "bg": "#0f0f0f",
    "surface": "#181818",
    "surface_alt": "#161616",      # sidebar / rails
    "surface_hover": "#242424",
    "input_bg": "#1e1e1e",
    "text": "#ececec",
    "text_secondary": "#9a9a9a",
    "text_faint": "#8a8a8a",       # WCAG AA: ≥4.5:1 on bg/surface (was #5c5c5c ≈ 2.9:1)
    "border": "#2a2a2a",
    "divider": "#242424",
    "accent": "#8c50dc",
    "accent_hover": "#7a3fc8",
    "accent_subtle": "rgba(140,80,220,0.16)",
    "on_accent": "#ffffff",
    "success": "#4ec77d",
    "warning": "#ffa028",
    "error": "#ff5a52",
}

_LIGHT = {
    "bg": "#faf7f2",               # warm cream (hero)
    "surface": "#ffffff",
    "surface_alt": "#f3ede4",      # sidebar / rails (warm)
    "surface_hover": "#efe7db",
    "input_bg": "#ffffff",
    "text": "#2b2823",
    "text_secondary": "#6b6459",
    "text_faint": "#756b5d",       # WCAG AA: ≥4.5:1 on the cream bg (was #a89e8f ≈ 2.5:1)
    "border": "#e6ddce",
    "divider": "#ece4d6",
    "accent": "#8c50dc",
    "accent_hover": "#7a3fc8",
    "accent_subtle": "rgba(140,80,220,0.12)",
    "on_accent": "#ffffff",
    "success": "#2ea866",
    "warning": "#c9770a",
    "error": "#d94b45",
}


def _relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of a #rrggbb color."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))

    def _lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG contrast ratio between two #rrggbb colors (1..21)."""
    l1, l2 = _relative_luminance(fg), _relative_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def tokens(scheme: str) -> dict:
    """Return a copy of the token dict for ``light`` or ``dark``."""
    return dict(_DARK if scheme == "dark" else _LIGHT)


# ---------- Active scheme state ----------
_STATE = {"scheme": "dark"}


def set_active_scheme(scheme: str) -> None:
    _STATE["scheme"] = "light" if scheme == "light" else "dark"


def active_scheme() -> str:
    return _STATE["scheme"]


def resolve_scheme(setting: str) -> str:
    """Map the ``theme`` setting (auto|light|dark) to a concrete scheme.

    ``auto`` follows the macOS system appearance via Qt's colorScheme hint.
    """
    if setting == "light":
        return "light"
    if setting == "dark":
        return "dark"
    try:
        cs = QGuiApplication.styleHints().colorScheme()
        return "light" if cs == Qt.ColorScheme.Light else "dark"
    except Exception:
        return "dark"


# ---------- Fonts ----------
_FONTS_LOADED = False


def load_fonts() -> None:
    """Register bundled Instrument Serif + Inter (idempotent). Must run after a
    QApplication exists and before ``setStyleSheet``."""
    global _FONTS_LOADED
    if _FONTS_LOADED:
        return
    files = [
        "InstrumentSerif-Regular.ttf",
        "InstrumentSerif-Italic.ttf",
        "Inter-Variable.ttf",
    ]
    for name in files:
        path = os.path.join(FONTS_DIR, name)
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)
    _FONTS_LOADED = True


# ---------- Live color proxy (legacy `C` API) ----------
_C_MAP = {
    "BG": "bg",
    "BG_ALT": "surface_alt",
    "BG_HOVER": "surface_hover",
    "BG_CARD": "surface",
    "BG_INPUT": "input_bg",
    "TEXT": "text",
    "TEXT_DIM": "text_secondary",
    "TEXT_FAINT": "text_faint",
    "ACCENT": "accent",
    "ACCENT_HOVER": "accent_hover",
    "ACCENT_SUBTLE": "accent_subtle",
    "DIVIDER": "divider",
    "BORDER": "border",
    "OK": "success",
    "WARN": "warning",
    "ERR": "error",
    "ON_ACCENT": "on_accent",
}


class _ColorProxy:
    """Attribute access resolves against the *active* scheme, so old inline
    stylesheets (``f"background: {C.BG}"``) become theme-aware automatically."""

    def __getattr__(self, name: str) -> str:
        t = tokens(active_scheme())
        key = _C_MAP.get(name)
        if key is not None:
            return t[key]
        low = name.lower()
        if low in t:
            return t[low]
        raise AttributeError(f"unknown color token: {name}")


C = _ColorProxy()


# ---------- Global stylesheet ----------
def qss(scheme: str) -> str:
    """Central application stylesheet for the given scheme. Applied via
    ``app.setStyleSheet``; targets widgets by class / objectName / role
    property so pages stop inlining duplicated QSS."""
    t = tokens(scheme)
    return f"""
    /* ---- base ---- */
    QWidget {{
        background: transparent;
        color: {t['text']};
        font-family: "{SANS}";
        font-size: 13px;
    }}
    QMainWindow, QDialog {{ background: {t['bg']}; }}
    QToolTip {{
        background: {t['surface']};
        color: {t['text']};
        border: 1px solid {t['border']};
        border-radius: {RADIUS_SM}px;
        padding: 5px 8px;
    }}

    /* ---- display / body type via `role` property ---- */
    /* `page` is the header every Hub page opens with: sans, so the serif keeps its
       impact on the brand/display surfaces (`display`) it's reserved for. */
    QLabel[role="page"]    {{ font-family: "{SANS}"; font-size: 28px; font-weight: 600; color: {t['text']}; }}
    QLabel[role="display"] {{ font-family: "{SERIF}"; font-size: 30px; color: {t['text']}; }}
    QLabel[role="title"]   {{ font-family: "{SERIF}"; font-size: 26px; color: {t['text']}; }}
    QLabel[role="heading"] {{ font-family: "{SANS}"; font-size: 15px; font-weight: 600; color: {t['text']}; }}
    QLabel[role="subtitle"]{{ font-family: "{SANS}"; font-size: 12px; color: {t['text_secondary']}; }}
    QLabel[role="caption"] {{ font-family: "{SANS}"; font-size: 11px; color: {t['text_faint']}; }}

    /* ---- buttons ---- */
    QPushButton#primary {{
        background: {t['accent']}; color: {t['on_accent']};
        border: none; border-radius: {RADIUS_SM}px;
        padding: 8px 16px; font-size: 13px; font-weight: 600;
    }}
    QPushButton#primary:hover {{ background: {t['accent_hover']}; }}
    QPushButton#primary:disabled {{ background: {t['surface_hover']}; color: {t['text_faint']}; }}

    QPushButton#secondary {{
        background: {t['surface']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: {RADIUS_SM}px;
        padding: 8px 16px; font-size: 13px; font-weight: 500;
    }}
    QPushButton#secondary:hover {{ background: {t['surface_hover']}; border-color: {t['accent']}; }}

    QPushButton#ghost {{
        background: transparent; color: {t['text_secondary']};
        border: none; border-radius: {RADIUS_SM}px; padding: 6px 10px;
    }}
    QPushButton#ghost:hover {{ background: {t['surface_hover']}; color: {t['text']}; }}

    QPushButton#icon {{
        background: {t['input_bg']}; color: {t['text_secondary']};
        border: 1px solid {t['border']}; border-radius: {RADIUS_SM}px;
    }}
    QPushButton#icon:hover {{ background: {t['surface_hover']}; color: {t['text']}; }}

    /* ---- inputs ---- */
    QLineEdit, QPlainTextEdit, QTextEdit {{
        background: {t['input_bg']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: {RADIUS_SM}px;
        padding: 8px 12px; font-size: 13px;
        selection-background-color: {t['accent']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {t['accent']}; }}
    QLineEdit::placeholder {{ color: {t['text_faint']}; }}

    /* ---- combo ---- */
    QComboBox {{
        background: {t['input_bg']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: {RADIUS_SM}px;
        padding: 7px 12px; font-size: 13px;
    }}
    QComboBox:hover {{ border-color: {t['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {t['surface']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: {RADIUS_SM}px;
        selection-background-color: {t['accent_subtle']};
        selection-color: {t['text']}; outline: none; padding: 4px;
    }}

    /* ---- switch toggle (styled QCheckBox indicator) ---- */
    QCheckBox {{ color: {t['text']}; font-size: 13px; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 38px; height: 22px; border-radius: 11px;
        background: {t['surface_hover']}; border: 1px solid {t['border']};
    }}
    QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; }}

    /* ---- tabs (underline) ---- */
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{
        background: transparent; color: {t['text_secondary']};
        padding: 8px 18px; margin-right: 2px; border: none;
        border-bottom: 2px solid transparent; font-size: 13px; font-weight: 500;
    }}
    QTabBar::tab:selected {{ color: {t['text']}; border-bottom: 2px solid {t['accent']}; }}
    QTabBar::tab:hover {{ color: {t['text']}; }}

    /* ---- menu (tray + context) ---- */
    QMenu {{
        background: {t['surface']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: {RADIUS_SM}px; padding: 6px;
    }}
    QMenu::item {{ padding: 6px 14px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {t['accent_subtle']}; }}
    QMenu::separator {{ height: 1px; background: {t['divider']}; margin: 5px 8px; }}

    /* ---- scrollbars ---- */
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {t['divider']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {t['surface_hover']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; width: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {t['divider']}; border-radius: 4px; min-width: 30px; }}
    QScrollBar::handle:horizontal:hover {{ background: {t['surface_hover']}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; height: 0; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

    /* ---- message boxes ---- */
    QMessageBox {{ background: {t['bg']}; }}
    QMessageBox QLabel {{ color: {t['text']}; font-size: 13px; }}
    QMessageBox QPushButton {{
        background: {t['surface']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: {RADIUS_SM}px;
        padding: 6px 16px; min-width: 72px;
    }}
    QMessageBox QPushButton:hover {{ background: {t['surface_hover']}; }}
    QMessageBox QPushButton:default {{ background: {t['accent']}; color: {t['on_accent']}; border: none; }}
    """
