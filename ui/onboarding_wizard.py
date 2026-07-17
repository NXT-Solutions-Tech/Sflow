"""Guided first-run: microphone, Accessibility, Input Monitoring, API key.

Replaces a single API-key dialog that asked for the one thing the default setup
does not need, while never mentioning the three permissions it does. Each of
those fails silently (see core/permissions.py), so the wizard's job is to turn
"nothing happens when I press the hotkey" into something the user can see and
fix while they're already looking at it.

Design notes:
- ``QDialog`` picks up ``background: bg`` from the global QSS for free; a plain
  QWidget would render transparent.
- Side effects (opening the mic stream, prompting TCC) live in ``on_enter``,
  which fires from ``showEvent`` — never ``__init__``. The offscreen preview
  harness grabs unshown widgets, so this keeps rendering side-effect free.
- The wizard always accepts. It can inform, but it must never be the reason the
  app doesn't start.
"""
from __future__ import annotations

from collections import deque

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from config import APP_DATA_DIR, LOGO_PATH
from core import onboarding, permissions
from core.i18n import tr
from core.onboarding import (
    STEP_ACCESSIBILITY, STEP_API_KEY, STEP_INPUT_MONITORING, STEP_MIC, STEP_MODEL,
    STEP_WELCOME,
)
from ui import icons, theme
from ui.audio_visualizer import AudioVisualizer
from ui.components import ghost_button, page_title, primary_button, secondary_button

_POLL_MS = 1000      # permission re-check cadence
_METER_MS = 100      # mic level sampling — 10Hz is plenty for a "we hear you"
_PEAK_WINDOW = 40    # ~4s of level history feeding mic_ok()


def _label(text: str, role: str, wrap: bool = True) -> QLabel:
    lb = QLabel(text)
    lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    return lb


class _StatusLine(QLabel):
    """Live "Concedido ✓" / "Pendiente" indicator. Colored inline because the
    token depends on state, which QSS roles can't express."""

    def __init__(self):
        super().__init__()
        self.setWordWrap(True)
        self.set_pending("Esperando…")

    def _paint(self, text: str, token: str):
        t = theme.tokens(theme.active_scheme())
        self.setText(text)
        self.setStyleSheet(f"color: {t[token]}; font-size: 13px; font-weight: 600;")

    def set_granted(self, text: str = "Concedido ✓"):
        self._paint(text, "success")

    def set_pending(self, text: str):
        self._paint(text, "text_secondary")

    def set_problem(self, text: str):
        self._paint(text, "warning")


class WizardStep(QWidget):
    """One screen. Subclasses override the hooks they need."""

    status_changed = pyqtSignal()
    step_id = ""

    def __init__(self):
        super().__init__()
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setSpacing(12)

    def header(self, icon_name: str, title: str, body: str):
        t = theme.tokens(theme.active_scheme())
        row = QHBoxLayout()
        row.setSpacing(10)
        glyph = QLabel()
        glyph.setPixmap(icons.icon(icon_name, color=t["accent"], size=26).pixmap(26, 26))
        row.addWidget(glyph)
        row.addWidget(page_title(title))
        row.addStretch()
        self.root.addLayout(row)
        self.root.addWidget(_label(body, "subtitle"))

    # --- hooks ---
    def on_enter(self):
        """Called when the step becomes visible. All side effects go here."""

    def on_leave(self):
        """Called when navigating away. Release anything on_enter acquired."""

    def can_continue(self) -> bool:
        return True

    def skip_label(self) -> str | None:
        """Text for the skip affordance, or None when the step is mandatory."""
        return None


class WelcomeStep(WizardStep):
    step_id = STEP_WELCOME

    def __init__(self):
        super().__init__()
        logo = QLabel()
        pm = QPixmap(LOGO_PATH)
        if not pm.isNull():
            logo.setPixmap(pm.scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
        self.root.addWidget(logo)

        # The serif display voice, reserved for brand moments like this one.
        hero = _label("Te damos la bienvenida a SFlow", "display")
        self.root.addWidget(hero)
        self.root.addWidget(_label(
            "Dictado por voz, privado y veloz. Tu voz se transcribe en este Mac — "
            "sin nube, sin suscripción.", "subtitle"))
        self.root.addWidget(_label(
            "Vamos a configurar el micrófono y dos permisos de macOS. Toma menos de un minuto.",
            "subtitle"))
        self.root.addStretch()


class MicStep(WizardStep):
    """Opens a real stream: it doubles as the macOS mic prompt and as proof the
    selected device actually produces signal — something a permission check
    alone can't tell you (an authorized mic can still be muted or dead)."""

    step_id = STEP_MIC

    def __init__(self):
        super().__init__()
        self.header("mic", "Prueba tu micrófono", "Di algo — deberías ver las barras moverse.")

        # AudioVisualizer paints hardcoded white bars (it was built for the dark
        # pill), so it gets a dark stage instead of being restyled.
        stage = QFrame()
        stage.setObjectName("vizStage")
        stage.setFixedHeight(72)
        stage.setStyleSheet("#vizStage { background: #16151a; border-radius: 12px; }")
        sl = QHBoxLayout(stage)
        sl.setContentsMargins(14, 10, 14, 10)
        self.viz = AudioVisualizer(parent=stage)
        sl.addWidget(self.viz)
        self.root.addWidget(stage)

        self.status = _StatusLine()
        self.root.addWidget(self.status)
        self.root.addStretch()

        self._recorder = None
        self._peaks: deque[float] = deque(maxlen=_PEAK_WINDOW)
        self._heard = False
        self._timer = QTimer(self)
        self._timer.setInterval(_METER_MS)
        self._timer.timeout.connect(self._sample)

    def on_enter(self):
        # Re-entrant safe: release any recorder still open before starting a new
        # one. Reassigning self._recorder without this would drop the previous
        # AudioRecorder while its PortAudio callback is still live — the C audio
        # thread then fires into a GC'd CFFI closure and the process segfaults.
        self._timer.stop()
        self.viz.stop()
        self._release()
        self.status.set_pending("Escuchando…")
        try:
            from core.recorder import AudioRecorder
            self._recorder = AudioRecorder()
            self._recorder.start()
        except Exception:
            # The recorder raises when macOS denies the mic.
            self._recorder = None
            self.status.set_problem("macOS bloqueó el micrófono. Ábrelo en Ajustes y vuelve.")
            return
        self.viz.set_audio_queue(self._recorder.audio_queue)
        self.viz.start()
        self._timer.start()

    def on_leave(self):
        self._timer.stop()
        self.viz.stop()
        self._release()

    def closeEvent(self, event):  # noqa: N802 - Qt
        # Belt and braces: SFlowApp opens its own stream right after the wizard
        # closes, and two live PortAudio streams can hang some devices.
        self._release()
        super().closeEvent(event)

    def _release(self):
        if self._recorder is not None:
            try:
                self._recorder.stop()
            except Exception:
                pass
            self._recorder = None

    def _sample(self):
        vals = getattr(self.viz, "bar_values", None) or [0.0]
        self._peaks.append(max(vals))
        if not self._heard and onboarding.mic_ok(list(self._peaks)):
            self._heard = True
            self.status.set_granted("Te escuchamos ✓")
            self.status_changed.emit()

    def skip_label(self) -> str | None:
        return "Saltar prueba"

    def open_settings(self):
        permissions.open_privacy_pane(permissions.PERM_MIC)


class _PermissionStep(WizardStep):
    """Shared shape for the two TCC steps: explain, prompt, poll until granted."""

    _perm = ""
    _pending_text = "Pendiente — concédelo en Ajustes del sistema"

    def __init__(self):
        super().__init__()
        self.status = _StatusLine()
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._granted = False

    def build_footer(self):
        self.root.addWidget(self.status)
        row = QHBoxLayout()
        row.setSpacing(8)
        open_btn = secondary_button("Abrir Ajustes del sistema")
        open_btn.clicked.connect(lambda: permissions.open_privacy_pane(self._perm))
        row.addWidget(open_btn)
        row.addStretch()
        self.root.addLayout(row)
        self.root.addStretch()

    def probe(self) -> bool | None:
        raise NotImplementedError

    def request(self):
        """Ask macOS to show its grant dialog, if it has one."""

    def on_enter(self):
        self.request()
        self._poll()
        self._timer.start()

    def on_leave(self):
        self._timer.stop()

    def _poll(self):
        state = self.probe()
        if state is True:
            self._granted = True
            self._timer.stop()
            self.status.set_granted()
        elif state is None:
            # Probe unavailable — say so rather than implying it's granted.
            self.status.set_pending("No se pudo verificar. Concédelo manualmente si el atajo no responde.")
        else:
            self.status.set_pending(self._pending_text)
        self.status_changed.emit()

    def skip_label(self) -> str | None:
        return None if self._granted else "Ahora no"


class AccessibilityStep(_PermissionStep):
    step_id = STEP_ACCESSIBILITY
    _perm = permissions.PERM_ACCESSIBILITY

    def __init__(self):
        super().__init__()
        self.header(
            "shield", "Permite escribir por ti",
            "SFlow escribe el texto dictado en la app donde estés. Sin este permiso "
            "la transcripción funciona, pero el texto nunca aparece.",
        )
        self._prompted = False
        self.build_footer()

    def probe(self):
        return permissions.accessibility_granted(prompt=False)

    def request(self):
        if not self._prompted:
            self._prompted = True
            permissions.accessibility_granted(prompt=True)


class InputMonitoringStep(_PermissionStep):
    step_id = STEP_INPUT_MONITORING
    _perm = permissions.PERM_INPUT_MONITORING

    def __init__(self):
        super().__init__()
        self.header(
            "keyboard", "Permite escuchar el atajo",
            "SFlow detecta Ctrl+Alt de forma global. Sin este permiso el atajo no "
            "responde y la app parece funcionar bien mientras no escucha nada.",
        )
        self._requested = False
        self.build_footer()

    def probe(self):
        return permissions.input_monitoring_granted()

    def request(self):
        # The preflight never prompts; this is the call that does.
        if not self._requested:
            self._requested = True
            permissions.request_input_monitoring()


class ApiKeyStep(WizardStep):
    """Optional by design: the default engine runs on-device."""

    step_id = STEP_API_KEY

    def __init__(self, key_required: bool = False):
        super().__init__()
        self._key_required = key_required
        # Calling it "optional" while refusing to continue without it would be a
        # lie; the copy follows the actual requirement.
        if key_required:
            self.header(
                "key", "Conecta Groq",
                "El modelo que elegiste transcribe en la nube, así que necesita una "
                "API key. Para dictar sin key, cambia a Whisper Turbo local en Ajustes.",
            )
        else:
            self.header(
                "key", "Conecta Groq (opcional)",
                "Solo hace falta para los modelos en la nube y la limpieza con IA. "
                "Whisper Turbo local no la necesita.",
            )

        t = theme.tokens(theme.active_scheme())
        link = QLabel(
            f'<a style="color:{t["accent"]}; text-decoration:none;" '
            'href="https://console.groq.com/keys">Obtener una gratis en console.groq.com/keys →</a>'
        )
        link.setOpenExternalLinks(True)
        self.root.addWidget(link)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("gsk_...")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.textChanged.connect(lambda _t: self.status.clear())
        self.root.addWidget(self.key_input)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color: {t['error']}; font-size: 12px;")
        self.root.addWidget(self.status)
        self.root.addStretch()

    def skip_label(self) -> str | None:
        # The whole point: an offline setup must be able to walk past this.
        return None if self._key_required else "Continuar sin conexión"

    def can_continue(self) -> bool:
        """Validate only what the user actually typed. An empty box is fine when
        the key is optional — the footer offers the offline path instead."""
        raw = self.key_input.text().strip()
        if not raw and not self._key_required:
            return True
        ok, err = onboarding.validate_api_key(raw)
        if not ok:
            self.status.setText(err)
            return False
        onboarding.store_api_key(raw, APP_DATA_DIR)
        return True


class ModelStep(WizardStep):
    """Optional upsell: Parakeet ships bundled, Whisper Turbo is a 1.6GB download
    for better accuracy. Always skippable — the default already works offline."""

    step_id = STEP_MODEL

    _WHISPER_REPO = "mlx-community/whisper-large-v3-turbo"

    def __init__(self):
        super().__init__()
        self.header("sparkles", tr("wizard.model_title"), tr("wizard.model_body"))
        self._btn = primary_button(tr("wizard.model_download"))
        self._btn.clicked.connect(self._download)
        self.root.addWidget(self._btn)
        self.status = _StatusLine()
        self.root.addWidget(self.status)
        self.root.addStretch()

    def on_enter(self):
        if ManagerCache.manager().is_available(self._WHISPER_REPO):
            self._btn.setEnabled(False)
            self.status.set_granted(tr("wizard.model_have_it"))

    def _download(self):
        from ui.model_download import ModelDownloadDialog
        dlg = ModelDownloadDialog(self._WHISPER_REPO, ManagerCache.manager(), self)
        dlg.exec()
        if ManagerCache.manager().is_available(self._WHISPER_REPO):
            self._btn.setEnabled(False)
            self.status.set_granted(tr("wizard.model_have_it"))

    def skip_label(self) -> str | None:
        return tr("wizard.model_later")  # always optional — bundled engine works

    def can_continue(self) -> bool:
        return True


class ManagerCache:
    """One ModelManager for the wizard's model step (avoids re-instantiating on
    every render)."""
    _mm = None

    @classmethod
    def manager(cls):
        if cls._mm is None:
            from core.models import ModelManager
            cls._mm = ModelManager()
        return cls._mm


class _StepDots(QWidget):
    """Progress dots. Painted rather than styled — QSS can't do this."""

    def __init__(self, total: int):
        super().__init__()
        self._total = total
        self._index = 0
        self.setFixedHeight(10)

    def set_index(self, i: int):
        self._index = i
        self.update()

    def paintEvent(self, _e):
        t = theme.tokens(theme.active_scheme())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        d, gap = 6, 8
        for i in range(self._total):
            p.setBrush(QColor(t["accent"] if i <= self._index else t["border"]))
            p.drawEllipse(i * (d + gap), 2, d, d)
        p.end()


class OnboardingWizard(QDialog):
    """Walks ``steps`` (ids from core.onboarding) and always accepts."""

    def __init__(self, steps: list[str], key_required: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SFlow")
        self.setModal(True)
        self.setFixedSize(560, 480)

        self._steps: list[WizardStep] = [self._build(s, key_required) for s in steps]
        self._index = 0
        # Which step index has already had on_enter() fired. showEvent can fire
        # repeatedly during macOS window setup, and _advance used to call
        # on_enter twice; entering the mic step twice orphaned a live PortAudio
        # stream (GC'd mid-callback → EXC_BAD_ACCESS). Guard: enter once per visit.
        self._entered_index = -1

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 26)
        root.setSpacing(16)

        self._dots = _StepDots(len(self._steps))
        root.addWidget(self._dots)

        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        root.addLayout(self._body, 1)
        for st in self._steps:
            st.setVisible(False)
            st.status_changed.connect(self._sync_footer)
            self._body.addWidget(st)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self._skip = ghost_button("")
        self._skip.clicked.connect(self._advance)
        footer.addWidget(self._skip)
        footer.addStretch()
        self._next = primary_button("Continuar")
        self._next.clicked.connect(self._on_next)
        footer.addWidget(self._next)
        root.addLayout(footer)

        self._show_step(0)

    @staticmethod
    def _build(step_id: str, key_required: bool) -> WizardStep:
        if step_id == STEP_MIC:
            return MicStep()
        if step_id == STEP_ACCESSIBILITY:
            return AccessibilityStep()
        if step_id == STEP_INPUT_MONITORING:
            return InputMonitoringStep()
        if step_id == STEP_API_KEY:
            return ApiKeyStep(key_required=key_required)
        if step_id == STEP_MODEL:
            return ModelStep()
        return WelcomeStep()

    @property
    def current(self) -> WizardStep:
        return self._steps[self._index]

    def _show_step(self, i: int):
        for n, st in enumerate(self._steps):
            st.setVisible(n == i)
        self._index = i
        self._entered_index = -1  # a fresh step has not been entered yet
        self._dots.set_index(i)
        self._sync_footer()
        if self.isVisible():
            self._enter_current()

    def _enter_current(self):
        """Fire the current step's on_enter exactly once per visit. showEvent
        can fire more than once; entering twice is what crashed the mic step."""
        if self._entered_index == self._index:
            return
        self._entered_index = self._index
        self.current.on_enter()

    def _sync_footer(self):
        label = self.current.skip_label()
        self._skip.setText(label or "")
        self._skip.setVisible(bool(label))
        last = self._index == len(self._steps) - 1
        self._next.setText("Empezar a dictar" if last else "Continuar")

    def _on_next(self):
        if not self.current.can_continue():
            return
        self._advance()

    def _advance(self):
        self.current.on_leave()
        self._entered_index = -1  # left the step; allow the next one to enter
        if self._index >= len(self._steps) - 1:
            self.accept()
            return
        self._show_step(self._index + 1)  # enters the new step exactly once

    def showEvent(self, event):  # noqa: N802 - Qt
        super().showEvent(event)
        # First step's side effects wait for a real show, so an unshown grab
        # (preview harness) never opens a mic stream or prompts for TCC. Guarded
        # so a repeat showEvent can't re-open (and orphan) the mic stream.
        self._enter_current()

    def closeEvent(self, event):  # noqa: N802 - Qt
        for st in self._steps:
            try:
                st.on_leave()
            except Exception:
                pass
        super().closeEvent(event)
