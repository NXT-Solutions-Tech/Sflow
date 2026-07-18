"""Reusable themed widgets + helpers for SFlow's design system.

Central QSS (ui/theme.qss) styles most controls by objectName/class. This module
holds the few things QSS can't express on its own — chiefly a real Switch toggle
with a sliding knob — plus tiny helpers to tag buttons with their QSS role.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QAbstractButton, QLabel, QPushButton, QWidget, QFrame,
    QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, pyqtProperty, QSize, QPointF,
)
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QLinearGradient, QPolygonF,
)

from ui import theme
from ui import icons


# ---------- Type helpers ----------
def page_title(text: str) -> QLabel:
    """The header a Hub page opens with — now in the Instrument Serif brand voice
    (was sans ``role="page"``), so every page shares Home's editorial display
    identity. Family/size come from an inline stylesheet (Qt's global
    ``QWidget{font-family:Inter}`` overrides ``setFont()``); the negative tracking
    is set via QFont since QSS has no letter-spacing property."""
    lb = serif_label(text, 28)
    f = lb.font()
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -0.3)
    lb.setFont(f)
    return lb


# ---------- Button role helpers ----------
def primary_button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("primary")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def secondary_button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("secondary")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def ghost_button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("ghost")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


# ---------- Switch toggle ----------
class Switch(QAbstractButton):
    """A Wispr-style on/off switch. Drop-in for QCheckBox where we only use
    isChecked()/setChecked()/toggled — same API, nicer look. Optional label is
    drawn to the right of the track."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._label = text
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._track_w = 40
        self._track_h = 22
        self._knob = 16
        self._margin = 3
        self._offset = 1.0 if self.isChecked() else 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.toggled.connect(self._on_toggled)

    # animated knob position 0..1
    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, v: float) -> None:
        self._offset = v
        self.update()

    offset = pyqtProperty(float, fget=_get_offset, fset=_set_offset)

    def _on_toggled(self, checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def setChecked(self, checked: bool) -> None:  # keep knob in sync w/o animation
        super().setChecked(checked)
        self._offset = 1.0 if checked else 0.0
        self.update()

    def sizeHint(self) -> QSize:
        w = self._track_w + 10
        if self._label:
            fm = self.fontMetrics()
            w += fm.horizontalAdvance(self._label) + 4
        return QSize(w, max(self._track_h, 24))

    def paintEvent(self, _event):
        t = theme.tokens(theme.active_scheme())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        track_x = 0
        track_y = (self.height() - self._track_h) // 2
        # track color lerps off->on
        off = QColor(t["surface_hover"])
        on = QColor(t["accent"])
        r = int(off.red() + (on.red() - off.red()) * self._offset)
        g = int(off.green() + (on.green() - off.green()) * self._offset)
        b = int(off.blue() + (on.blue() - off.blue()) * self._offset)
        p.setPen(Qt.PenStyle.NoPen)
        if self._offset < 0.5:
            p.setPen(QColor(t["border"]))
        p.setBrush(QColor(r, g, b))
        p.drawRoundedRect(track_x, track_y, self._track_w, self._track_h,
                          self._track_h // 2, self._track_h // 2)

        # knob
        travel = self._track_w - self._knob - 2 * self._margin
        kx = track_x + self._margin + travel * self._offset
        ky = track_y + self._margin
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(int(kx), int(ky), self._knob, self._knob)

        # label
        if self._label:
            p.setPen(QColor(t["text"]))
            f = QFont(theme.SANS)
            f.setPixelSize(13)
            p.setFont(f)
            tx = self._track_w + 10
            p.drawText(tx, 0, self.width() - tx, self.height(),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                       self._label)
        p.end()


# ---------- Color helpers ----------
def _qcolor(token_value: str) -> QColor:
    """Build a QColor from a token — handles both ``#rrggbb`` and
    ``rgba(r,g,b,a)`` (Qt's QColor(str) can't parse the CSS rgba() form)."""
    v = token_value.strip()
    if v.startswith("rgba(") or v.startswith("rgb("):
        nums = v[v.index("(") + 1:v.rindex(")")].split(",")
        r, g, b = (int(float(nums[i])) for i in range(3))
        a = int(float(nums[3]) * 255) if len(nums) > 3 else 255
        return QColor(r, g, b, a)
    return QColor(v)


# ---------- Elevation ----------
_ELEVATION = {"sm": (14, 3), "md": (26, 7), "lg": (40, 12)}


def elevate(widget: QWidget, level: str = "md") -> QWidget:
    """Give a card real depth with a themed drop shadow — the only way to cast a
    shadow in Qt (QSS has no ``box-shadow``). Pair with a ``surface_raised`` fill
    so the hierarchy survives where a shadow can't render (offscreen, low-DPI)."""
    blur, dy = _ELEVATION.get(level, _ELEVATION["md"])
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setXOffset(0)
    eff.setYOffset(dy)
    eff.setColor(_qcolor(theme.tokens(theme.active_scheme())["shadow"]))
    widget.setGraphicsEffect(eff)
    return widget


# ---------- Type helpers (serif brand voice) ----------
def serif_label(text: str, size: int, color: str | None = None) -> QLabel:
    """A label in the Instrument Serif brand face. The family/size go through an
    inline stylesheet — Qt's global ``QWidget{font-family:Inter}`` rule overrides
    ``setFont()``, so only a stylesheet (higher cascade priority) makes the serif
    stick. Letter-spacing, which QSS can't express, is still set via QFont."""
    lb = QLabel(text)
    col = color if color is not None else theme.C.TEXT
    lb.setStyleSheet(
        f'font-family: "{theme.SERIF}"; font-size: {size}px;'
        f" color: {col}; background: transparent;"
    )
    return lb


def display_title(text: str, size: int = 34) -> QLabel:
    """A large Instrument Serif header — the brand display voice, for page/section
    heroes."""
    return serif_label(text, size)


# ---------- Icon badge ----------
def icon_badge(icon_name: str, *, size: int = 36, glyph: int = 18,
               accent: bool = True) -> QLabel:
    """A Lucide glyph centered in a soft rounded chip — the recurring 'metric has
    an icon' motif. Accent chips use ``accent_soft`` + accent glyph; neutral ones
    use the input surface + dim glyph."""
    lb = QLabel()
    lb.setFixedSize(size, size)
    lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    color = theme.C.ACCENT if accent else theme.C.TEXT_DIM
    lb.setPixmap(icons.pixmap(icon_name, color=color, size=glyph))
    bg = theme.C.ACCENT_SOFT if accent else theme.C.BG_INPUT
    lb.setStyleSheet(f"background: {bg}; border-radius: {size // 2}px;")
    return lb


# ---------- Stat card ----------
class StatCard(QFrame):
    """Elevated dashboard tile: icon badge + big serif value + caption. One accent
    focal point per card. Replaces the flat ``_stat_card`` boxes duplicated across
    Home and Insights."""

    def __init__(self, icon_name: str, value: str, label: str,
                 accent: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        t = theme.tokens(theme.active_scheme())
        self.setStyleSheet(
            f"#statCard {{ background: {t['surface_raised']};"
            f" border: 1px solid {t['border']}; border-radius: 14px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 15, 16, 15)
        lay.setSpacing(12)

        lay.addWidget(icon_badge(icon_name, accent=accent),
                      alignment=Qt.AlignmentFlag.AlignLeft)

        lay.addWidget(serif_label(value, 34, t["accent"] if accent else t["text"]))

        cap = QLabel(label)
        cap.setStyleSheet(f"color: {t['text_secondary']}; font-size: 12px; background: transparent;")
        lay.addWidget(cap)

        elevate(self, "md")


# ---------- Keycap ----------
def keycap(text: str) -> QLabel:
    """One keyboard-key chip (``Ctrl``, ``Alt``). Bordered, rounded, mono-ish —
    reads as a physical key, not README bold text."""
    t = theme.tokens(theme.active_scheme())
    lb = QLabel(text)
    lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    f = QFont(theme.SANS)
    f.setPixelSize(12)
    f.setWeight(QFont.Weight.DemiBold)
    lb.setFont(f)
    lb.setStyleSheet(
        f"color: {t['text']}; background: {t['input_bg']};"
        f" border: 1px solid {t['border']}; border-bottom: 2px solid {t['border']};"
        f" border-radius: 6px; padding: 2px 8px;"
    )
    return lb


def keycaps(*keys: str) -> QWidget:
    """A row of keycaps joined by dim ``+`` separators."""
    t = theme.tokens(theme.active_scheme())
    host = QWidget()
    row = QHBoxLayout(host)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(5)
    for i, k in enumerate(keys):
        if i:
            plus = QLabel("+")
            plus.setStyleSheet(f"color: {t['text_faint']}; font-size: 12px; background: transparent;")
            row.addWidget(plus)
        row.addWidget(keycap(k))
    row.addStretch()
    return host


# ---------- Sparkline ----------
class Sparkline(QWidget):
    """A tiny custom-painted trend line (accent stroke + gradient fill). Theme-aware
    because it reads tokens in ``paintEvent`` — it re-skins on the next repaint."""

    def __init__(self, values=None, parent=None):
        super().__init__(parent)
        self._values = list(values or [])
        self.setMinimumHeight(48)

    def set_values(self, values) -> None:
        self._values = list(values or [])
        self.update()

    def paintEvent(self, _event):
        vals = self._values
        w, h = self.width(), self.height()
        if w <= 2 or h <= 2:
            return
        t = theme.tokens(theme.active_scheme())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        pad = 3
        n = len(vals)
        lo, hi = (min(vals), max(vals)) if vals else (0, 0)
        span = (hi - lo) or 1

        def _pt(i, v):
            x = pad + (w - 2 * pad) * (i / (n - 1)) if n > 1 else w / 2
            y = (h - pad) - (h - 2 * pad) * ((v - lo) / span)
            return QPointF(x, y)

        if n == 0:
            p.end()
            return
        if n == 1:
            vals = vals * 2
            n = 2

        line = QPolygonF([_pt(i, v) for i, v in enumerate(vals)])

        # gradient fill under the line
        fill = QPolygonF(line)
        fill.append(QPointF(w - pad, h))
        fill.append(QPointF(pad, h))
        grad = QLinearGradient(0, 0, 0, h)
        acc = _qcolor(t["accent"])
        top = QColor(acc); top.setAlpha(90)
        bot = QColor(acc); bot.setAlpha(0)
        grad.setColorAt(0.0, top)
        grad.setColorAt(1.0, bot)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawPolygon(fill)

        # the line itself
        pen = QPen(acc)
        pen.setWidthF(2.0)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolyline(line)
        p.end()


# ---------- Empty state ----------
class EmptyState(QWidget):
    """Centered icon-in-chip + message (+ optional hint). Replaces the bare gray
    one-liners on Home / Insights / Snippets."""

    def __init__(self, icon_name: str, text: str, hint: str | None = None, parent=None):
        super().__init__(parent)
        t = theme.tokens(theme.active_scheme())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 36, 24, 36)
        lay.setSpacing(12)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lay.addWidget(icon_badge(icon_name, size=52, glyph=24, accent=False),
                      alignment=Qt.AlignmentFlag.AlignHCenter)

        msg = QLabel(text)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {t['text']}; font-size: 14px; font-weight: 600; background: transparent;")
        lay.addWidget(msg)

        if hint:
            sub = QLabel(hint)
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setWordWrap(True)
            sub.setStyleSheet(f"color: {t['text_faint']}; font-size: 12px; background: transparent;")
            lay.addWidget(sub)
