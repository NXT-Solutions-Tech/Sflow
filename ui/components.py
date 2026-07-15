"""Reusable themed widgets + helpers for SFlow's design system.

Central QSS (ui/theme.qss) styles most controls by objectName/class. This module
holds the few things QSS can't express on its own — chiefly a real Switch toggle
with a sliding knob — plus tiny helpers to tag buttons with their QSS role.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QAbstractButton, QPushButton
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtProperty, QSize
from PyQt6.QtGui import QPainter, QColor, QFont

from ui import theme


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
