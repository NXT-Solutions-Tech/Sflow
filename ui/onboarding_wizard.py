"""Guided first-run wizard — replaces the old single-field FirstRunDialog.

Multi-step flow that walks a brand-new user through the three permissions the
app silently depends on, then an *optional* API key:

    Bienvenida → Micrófono (live level meter) → Accesibilidad (live poll)
               → Input Monitoring (guided) → API key (opcional si local)

Design notes
------------
* Styled with the app's existing dark palette + blue accent (matches the Hub);
  no external assets, 100% offline.
* This is an ordinary modal QDialog — it does NOT touch the pill/Hub/red_dot
  native window flags.
* All decision logic (is a key required? is Accessibility granted?) lives in the
  headless-testable ``core.onboarding`` module; this file is only the UI shell.
"""
import os

from PyQt6.QtWidgets import (
    QDialog, QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QPixmap

from config import LOGO_PATH, APP_DATA_DIR
from core.recorder import AudioRecorder
from core.onboarding import (
    api_key_required, is_groq_key_valid, accessibility_trusted,
    open_settings_pane, ACCESSIBILITY_PANE, INPUT_MONITORING_PANE,
)


# ---------- Palette (matches ui/hub_window.py `class C`) ----------
class C:
    BG = "#0f0f0f"
    BG_CARD = "#181818"
    BG_INPUT = "#202020"
    TEXT = "#e8e8e8"
    TEXT_DIM = "#8a8a8a"
    TEXT_FAINT = "#555555"
    ACCENT = "#5a9fff"
    DIVIDER = "#2a2a2a"
    OK = "#50d278"
    ERR = "#ff4646"


def _primary_btn(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(f"""
        QPushButton {{
            background: {C.ACCENT}; color: #08131f; font-size: 13px;
            font-weight: 600; border: none; border-radius: 8px;
            padding: 9px 18px;
        }}
        QPushButton:hover {{ background: #6fb0ff; }}
        QPushButton:disabled {{ background: #2a3a4d; color: {C.TEXT_FAINT}; }}
    """)
    return b


def _secondary_btn(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(f"""
        QPushButton {{
            background: transparent; color: {C.TEXT_DIM}; font-size: 13px;
            border: 1px solid {C.DIVIDER}; border-radius: 8px; padding: 9px 18px;
        }}
        QPushButton:hover {{ color: {C.TEXT}; border-color: {C.TEXT_FAINT}; }}
        QPushButton:disabled {{ color: {C.TEXT_FAINT}; border-color: {C.DIVIDER}; }}
    """)
    return b


def _title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {C.TEXT}; font-size: 21px; font-weight: 600;")
    lbl.setWordWrap(True)
    return lbl


def _body(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 13px; line-height: 1.5;")
    lbl.setWordWrap(True)
    return lbl


class OnboardingWizard(QDialog):
    """Modal guided setup. Call ``.exec()``; Accepted == user finished setup."""

    STEPS = ["welcome", "microphone", "accessibility", "input_monitoring", "api_key"]

    def __init__(self, recorder: AudioRecorder | None = None):
        super().__init__()
        self.setWindowTitle("SFlow — Bienvenido")
        self.setFixedSize(QSize(540, 500))
        self.setStyleSheet(f"background: {C.BG};")

        # Reuse the app's recorder if one is passed (avoids grabbing the device
        # twice); otherwise own a throwaway one just for the mic test.
        self._recorder = recorder or AudioRecorder()
        self._owns_recorder = recorder is None
        self._mic_active = False
        self._acc_granted = False

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 22)
        root.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_welcome())
        self.stack.addWidget(self._page_microphone())
        self.stack.addWidget(self._page_accessibility())
        self.stack.addWidget(self._page_input_monitoring())
        self.stack.addWidget(self._page_api_key())
        root.addWidget(self.stack, 1)

        # Progress dots + nav
        self._dots = QLabel()
        self._dots.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 12px;")
        nav = QHBoxLayout()
        nav.setContentsMargins(0, 14, 0, 0)
        nav.addWidget(self._dots)
        nav.addStretch(1)
        self.back_btn = _secondary_btn("Atrás")
        self.back_btn.clicked.connect(lambda: self._go(-1))
        self.next_btn = _primary_btn("Comenzar")
        self.next_btn.clicked.connect(lambda: self._go(+1))
        nav.addWidget(self.back_btn)
        nav.addSpacing(8)
        nav.addWidget(self.next_btn)
        root.addLayout(nav)

        # Live-poll timers
        self._mic_timer = QTimer(self)
        self._mic_timer.setInterval(60)
        self._mic_timer.timeout.connect(self._poll_mic_level)
        self._acc_timer = QTimer(self)
        self._acc_timer.setInterval(1000)
        self._acc_timer.timeout.connect(self._poll_accessibility)

        self._sync_nav()

    # ------------------------------------------------------------------ pages
    def _page_welcome(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)
        lay.addSpacing(10)

        logo = QLabel()
        pix = QPixmap(LOGO_PATH)
        if not pix.isNull():
            logo.setPixmap(pix.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(logo)

        lay.addWidget(_title("Bienvenido a SFlow"))
        lay.addWidget(_body(
            "Dicta con la voz en cualquier app y SFlow pega el texto donde esté "
            "tu cursor. En unos pasos concedemos los permisos necesarios para "
            "que todo funcione — sin sorpresas ni fallos silenciosos.\n\n"
            "Por defecto SFlow transcribe 100% local (offline). La conexión "
            "con la nube es opcional."
        ))
        lay.addStretch(1)
        return w

    def _page_microphone(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)
        lay.addWidget(_title("Micrófono"))
        lay.addWidget(_body(
            "SFlow necesita el micrófono para escucharte. Pulsa «Probar» y "
            "di algo — deberías ver moverse el medidor. macOS pedirá permiso "
            "la primera vez."
        ))

        self._mic_test_btn = _secondary_btn("Probar micrófono")
        self._mic_test_btn.clicked.connect(self._toggle_mic_test)
        lay.addWidget(self._mic_test_btn)

        self._mic_meter = QProgressBar()
        self._mic_meter.setRange(0, 100)
        self._mic_meter.setValue(0)
        self._mic_meter.setTextVisible(False)
        self._mic_meter.setFixedHeight(14)
        self._mic_meter.setStyleSheet(f"""
            QProgressBar {{
                background: {C.BG_INPUT}; border: 1px solid {C.DIVIDER};
                border-radius: 7px;
            }}
            QProgressBar::chunk {{ background: {C.ACCENT}; border-radius: 6px; }}
        """)
        lay.addWidget(self._mic_meter)

        self._mic_status = QLabel("")
        self._mic_status.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px;")
        lay.addWidget(self._mic_status)
        lay.addStretch(1)
        return w

    def _page_accessibility(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)
        lay.addWidget(_title("Accesibilidad"))
        lay.addWidget(_body(
            "Para pegar el texto por ti, SFlow necesita permiso de "
            "Accesibilidad. Abre Ajustes, activa SFlow en la lista y esta "
            "ventana lo detectará automáticamente.\n\n"
            "Nota: tras cada rebuild de la app, macOS revoca este permiso — "
            "si el pegado deja de funcionar, vuelve aquí."
        ))
        self._acc_open_btn = _secondary_btn("Abrir Ajustes de Accesibilidad")
        self._acc_open_btn.clicked.connect(
            lambda: open_settings_pane(ACCESSIBILITY_PANE)
        )
        lay.addWidget(self._acc_open_btn)

        self._acc_status = QLabel("Esperando permiso…")
        self._acc_status.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 13px;")
        lay.addWidget(self._acc_status)
        lay.addStretch(1)
        return w

    def _page_input_monitoring(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)
        lay.addWidget(_title("Input Monitoring"))
        lay.addWidget(_body(
            "Los atajos de teclado (Ctrl+Alt para dictar) usan Input "
            "Monitoring. Sin este permiso los atajos fallan EN SILENCIO — "
            "la app parece encendida pero no reacciona a las teclas.\n\n"
            "Abre Ajustes, activa SFlow en «Input Monitoring» y vuelve aquí."
        ))
        self._im_open_btn = _secondary_btn("Abrir Ajustes de Input Monitoring")
        self._im_open_btn.clicked.connect(
            lambda: open_settings_pane(INPUT_MONITORING_PANE)
        )
        lay.addWidget(self._im_open_btn)

        hint = QLabel("Cuando lo hayas activado, pulsa «Continuar».")
        hint.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 12px;")
        lay.addWidget(hint)
        lay.addStretch(1)
        return w

    def _page_api_key(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(12)
        self._key_title = _title("API key (opcional)")
        lay.addWidget(self._key_title)
        self._key_body = _body("")
        lay.addWidget(self._key_body)

        link = QLabel(
            '<a style="color:#5a9fff;" '
            'href="https://console.groq.com/keys">Obtener gratis en '
            'console.groq.com/keys</a>'
        )
        link.setOpenExternalLinks(True)
        link.setStyleSheet("font-size: 12px;")
        lay.addWidget(link)

        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("gsk_…")
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.BG_INPUT}; color: {C.TEXT};
                border: 1px solid {C.DIVIDER}; border-radius: 8px;
                padding: 9px 11px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {C.ACCENT}; }}
        """)
        self._key_input.textChanged.connect(self._sync_nav)
        lay.addWidget(self._key_input)

        self._key_hint = QLabel("")
        self._key_hint.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 12px;")
        self._key_hint.setWordWrap(True)
        lay.addWidget(self._key_hint)
        lay.addStretch(1)
        return w

    # ---------------------------------------------------------------- helpers
    def _current(self) -> int:
        return self.stack.currentIndex()

    def _is_last(self) -> bool:
        return self._current() == self.stack.count() - 1

    def _go(self, delta: int):
        idx = self._current()
        if delta > 0 and self._is_last():
            self._finish()
            return
        new = max(0, min(self.stack.count() - 1, idx + delta))
        if new == idx:
            return
        self._leave(idx)
        self.stack.setCurrentIndex(new)
        self._enter(new)
        self._sync_nav()

    def _enter(self, idx: int):
        page = self.STEPS[idx] if idx < len(self.STEPS) else ""
        if page == "accessibility":
            # Register SFlow in the Accessibility list + prompt, then poll.
            self._acc_granted = accessibility_trusted(prompt=True)
            self._refresh_acc_status()
            if not self._acc_granted:
                self._acc_timer.start()
        elif page == "api_key":
            self._refresh_key_page()

    def _leave(self, idx: int):
        page = self.STEPS[idx] if idx < len(self.STEPS) else ""
        if page == "microphone":
            self._stop_mic_test()
        elif page == "accessibility":
            self._acc_timer.stop()

    def _sync_nav(self):
        idx = self._current()
        self.back_btn.setEnabled(idx > 0)
        self._dots.setText("  ".join(
            "●" if i == idx else "○" for i in range(self.stack.count())
        ))
        if self._is_last():
            required = api_key_required()
            if required:
                self.next_btn.setText("Finalizar")
                self.next_btn.setEnabled(is_groq_key_valid(self._key_input.text()))
            else:
                txt = self._key_input.text().strip()
                self.next_btn.setText(
                    "Finalizar" if txt else "Continuar sin conexión / offline"
                )
                # Optional: allow finishing with empty key, but block a
                # half-typed invalid key.
                self.next_btn.setEnabled(not txt or is_groq_key_valid(txt))
        elif idx == 0:
            self.next_btn.setText("Comenzar")
            self.next_btn.setEnabled(True)
        else:
            self.next_btn.setText("Continuar")
            self.next_btn.setEnabled(True)

    # -------------------------------------------------------------- mic test
    def _toggle_mic_test(self):
        if self._mic_active:
            self._stop_mic_test()
        else:
            self._start_mic_test()

    def _start_mic_test(self):
        try:
            self._recorder.start()
            self._mic_active = True
            self._mic_test_btn.setText("Detener prueba")
            self._mic_status.setText("Escuchando… di algo.")
            self._mic_status.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px;")
            self._mic_timer.start()
        except Exception as e:
            self._mic_status.setText(f"No se pudo abrir el micrófono: {e}")
            self._mic_status.setStyleSheet(f"color: {C.ERR}; font-size: 12px;")

    def _stop_mic_test(self):
        if not self._mic_active:
            return
        self._mic_timer.stop()
        try:
            self._recorder.stop()
        except Exception:
            pass
        self._mic_active = False
        self._mic_meter.setValue(0)
        self._mic_test_btn.setText("Probar micrófono")

    def _poll_mic_level(self):
        try:
            import numpy as np
            q = self._recorder.audio_queue
            level = 0.0
            while not q.empty():
                chunk = q.get_nowait()
                rms = float(np.sqrt(np.mean(np.square(chunk.astype("float32")))))
                level = max(level, rms / 32768.0)
            if level > 0:
                # Perceptual-ish scaling so quiet speech still moves the bar.
                pct = min(100, int((level ** 0.5) * 180))
                self._mic_meter.setValue(pct)
                if pct > 12:
                    self._mic_status.setText("Te escuché ✓")
                    self._mic_status.setStyleSheet(
                        f"color: {C.OK}; font-size: 12px; font-weight: 600;"
                    )
        except Exception:
            pass

    # -------------------------------------------------------- accessibility
    def _poll_accessibility(self):
        if accessibility_trusted(prompt=False):
            self._acc_granted = True
            self._acc_timer.stop()
        self._refresh_acc_status()

    def _refresh_acc_status(self):
        if self._acc_granted:
            self._acc_status.setText("Concedido ✓")
            self._acc_status.setStyleSheet(
                f"color: {C.OK}; font-size: 13px; font-weight: 600;"
            )
        else:
            self._acc_status.setText("Esperando permiso…")
            self._acc_status.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 13px;")

    # ------------------------------------------------------------- api key
    def _refresh_key_page(self):
        if api_key_required():
            self._key_title.setText("API key requerida")
            self._key_body.setText(
                "El modelo de transcripción activo usa la nube (o tienes Auto "
                "Cleanup activado), así que necesitas una Groq API key para "
                "continuar. Es gratis."
            )
            self._key_hint.setText("Requerida por el modelo/limpieza activos.")
        else:
            self._key_title.setText("API key (opcional)")
            self._key_body.setText(
                "SFlow ya funciona 100% offline con el modelo local. Si quieres "
                "usar la nube como respaldo o Auto Cleanup, pega tu Groq API "
                "key. Si no, continúa sin conexión."
            )
            self._key_hint.setText("Opcional — puedes añadirla luego en Ajustes.")

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_nav()

    # -------------------------------------------------------------- finish
    def _save_key(self, key: str):
        """Persist the Groq key to Keychain (fallback .env) + live env."""
        key = key.strip()
        if not key:
            return
        stored = False
        try:
            from core.secrets import set_key
            stored = set_key("GROQ_API_KEY", key)
        except Exception:
            stored = False
        if not stored:
            try:
                os.makedirs(APP_DATA_DIR, exist_ok=True)
                with open(os.path.join(APP_DATA_DIR, ".env"), "w") as f:
                    f.write(f"GROQ_API_KEY={key}\n")
            except Exception:
                pass
        os.environ["GROQ_API_KEY"] = key

    def _finish(self):
        key = self._key_input.text().strip()
        if key:
            if not is_groq_key_valid(key):
                self._key_hint.setText(
                    "La clave debe empezar por 'gsk_' y tener ≥20 caracteres."
                )
                self._key_hint.setStyleSheet(f"color: {C.ERR}; font-size: 12px;")
                return
            self._save_key(key)
        self._stop_mic_test()
        self._acc_timer.stop()
        self.accept()

    def reject(self):
        self._stop_mic_test()
        self._acc_timer.stop()
        super().reject()

    def closeEvent(self, event):
        self._stop_mic_test()
        self._acc_timer.stop()
        super().closeEvent(event)
