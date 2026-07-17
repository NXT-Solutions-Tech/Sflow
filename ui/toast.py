"""In-app toast — the guaranteed, always-visible error surface.

macOS can swallow tray notifications (Do Not Disturb, unsigned dev builds), so
"the only guaranteed feedback is a 1.2s red X" was a real gap. This panel is a
non-activating floating window (same native trick as the pill) that fades in near
the top-right, auto-dismisses, and queues so a burst of errors doesn't stack.

``ToastManager.show(toast)`` is the entry point; ``main.notify()`` calls it first
and keeps ``tray.showMessage`` only as a backup.
"""
from collections import deque

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication

from ui import theme

try:
    from ctypes import c_void_p
    import AppKit
    import objc
    _HAVE_COCOA = True
except Exception:
    _HAVE_COCOA = False


class _ToastWidget(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(320)
        t = theme.tokens(theme.active_scheme())
        self._t = t
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(3)
        self._title = QLabel()
        self._title.setStyleSheet(f"color: {t['text']}; font-size: 13px; font-weight: 600;")
        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setStyleSheet(f"color: {t['text_secondary']}; font-size: 12px;")
        root.addWidget(self._title)
        root.addWidget(self._body)
        self.setStyleSheet(
            f"background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 12px;"
        )

    def set_content(self, title: str, body: str):
        self._title.setText(title)
        self._body.setText(body)
        self.adjustSize()

    def _setup_native(self):
        if not _HAVE_COCOA:
            return
        # The offscreen platform (tests, preview harness) has no real NSWindow;
        # poking winId() into objc there segfaults. Skip — native floating is a
        # production-only concern.
        app = QApplication.instance()
        if app is not None and app.platformName() == "offscreen":
            return
        wid = int(self.winId())
        if not wid:
            return
        try:
            ns_view = objc.objc_object(c_void_p=c_void_p(wid))
            ns_window = ns_view.window()
            ns_window.setLevel_(AppKit.NSFloatingWindowLevel)
            ns_window.setStyleMask_(ns_window.styleMask() | AppKit.NSWindowStyleMaskNonactivatingPanel)
            ns_window.setHidesOnDeactivate_(False)
            ns_window.setCollectionBehavior_(
                AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
                | AppKit.NSWindowCollectionBehaviorStationary
                | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
            )
        except Exception:
            pass

    def place_top_right(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        self.move(geo.right() - self.width() - 20, geo.top() + 20)


class ToastManager:
    """Owns one reusable toast widget + a queue. Auto-dismisses each toast and
    shows the next. Safe to construct without a display (defers widget creation)."""

    def __init__(self, duration_ms: int = 4000):
        self._duration = duration_ms
        self._widget: _ToastWidget | None = None
        self._queue: deque = deque()
        self._timer: QTimer | None = None
        self._showing = False

    def _ensure_widget(self):
        if self._widget is None:
            self._widget = _ToastWidget()
            self._widget._setup_native()
            self._timer = QTimer(self._widget)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._dismiss)

    def show(self, toast):
        """Enqueue a toast (a NamedTuple with .title/.body) and display it."""
        self._queue.append((toast.title, toast.body))
        if not self._showing:
            self._advance()

    def _advance(self):
        if not self._queue:
            self._showing = False
            return
        title, body = self._queue.popleft()
        self._ensure_widget()
        self._showing = True
        self._widget.set_content(title, body)
        self._widget.place_top_right()
        self._widget.show()
        self._widget.raise_()
        self._timer.start(self._duration)

    def _dismiss(self):
        if self._widget:
            self._widget.hide()
        if self._queue:
            self._advance()
        else:
            self._showing = False
