#!/usr/bin/env python3
"""SFlow — Voice-to-text desktop tool. Local Whisper Turbo / Parakeet (offline,
default) with Groq cloud fallback, LLM cleanup, per-app tone, Command Mode,
and a light+dark native Hub."""

import os
import sys
import signal
import subprocess
import threading
import traceback
import multiprocessing

# CRITICO en un .app congelado (PyInstaller): numba/librosa (motores locales)
# lanzan procesos con multiprocessing (start method "spawn" en macOS), que
# re-ejecutan el binario. Sin freeze_support(), cada worker cae en main() y
# ABRE OTRA VENTANA (pill). freeze_support() intercepta al worker y lo hace
# salir antes de llegar a main(). Debe ser lo PRIMERO que corre.
multiprocessing.freeze_support()
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu,
    QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon, QPixmap, QAction

from ui.pill_widget import PillWidget
from ui.hub_window import HubWindow
from ui.red_dot_indicator import RedDotIndicator
from core.recorder import AudioRecorder
from core.transcriber import Transcriber
from core.transcriber_groq import GroqTranscriber
from core.hotkey import HotkeyListener
from core.paste import paste_text, paste_last_transcript, save_frontmost_app
from core.command_mode import CommandModeHandler, copy_selection
from core.transform import TransformHandler
from core.relaunch import relaunch_app
from core.logger import log, log_exc
from db.database import TranscriptionDB
from config import LOGO_PATH, APP_DATA_DIR, AUDIO_DIR, get_setting, get_stt_model
from ui import theme


def _was_cloud_fallback(model_id: str) -> bool:
    """True when the user picked a LOCAL engine but the router transcribed in the
    cloud anyway (local engine unavailable or failed mid-run). The audio left the
    device, so the pill must say so instead of flashing a plain success check."""
    active = get_stt_model()
    return bool(active.get("local")) and model_id != active.get("model")


def apply_theme(app: QApplication) -> str:
    """Load bundled fonts and apply the global stylesheet for the resolved
    scheme (auto→system, or the forced light/dark setting). Returns the scheme."""
    theme.load_fonts()
    scheme = theme.resolve_scheme(get_setting("theme", "auto"))
    theme.set_active_scheme(scheme)
    app.setStyleSheet(theme.qss(scheme))
    return scheme


def _ensure_accessibility() -> bool:
    """Check Accessibility permission. Triggers macOS prompt on first call.

    After every .app rebuild the ad-hoc code signature changes, so macOS
    silently revokes Accessibility — keystroke paste then fails without an
    error. We detect that and open the Privacy panel so the user can re-add
    SFlow without hunting through System Settings.
    """
    trusted = True
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions
        trusted = bool(AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True}))
    except Exception:
        return True

    if not trusted:
        try:
            subprocess.Popen([
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            ])
        except Exception:
            pass
        try:
            QMessageBox.warning(
                None,
                "SFlow necesita Accessibility",
                "Después de un rebuild macOS revoca el permiso. Abre System Settings → "
                "Privacy & Security → Accessibility y vuelve a marcar SFlow. "
                "Luego reinicia la app desde el menu del tray.",
            )
        except Exception:
            pass
    return trusted


_LAUNCH_AGENT_LABEL = "so.saasfactory.sflow"
_PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{_LAUNCH_AGENT_LABEL}.plist")


class FirstRunDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SFlow")
        self.setFixedWidth(460)

        from ui import theme
        accent = theme.tokens(theme.active_scheme())["accent"]
        dim = theme.tokens(theme.active_scheme())["text_secondary"]

        layout = QVBoxLayout()
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(14)

        # Brand mark
        logo = QLabel()
        pm = QPixmap(LOGO_PATH)
        if not pm.isNull():
            logo.setPixmap(pm.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(logo)

        title = QLabel("Te damos la bienvenida a SFlow")
        title.setStyleSheet(f"font-family: 'Instrument Serif'; font-size: 30px;")
        layout.addWidget(title)

        sub = QLabel("Dictado por voz, privado y veloz. Para empezar, pega tu Groq API "
                     "key — se usa para la transcripción en la nube (los modelos locales "
                     "no la necesitan).")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {dim}; font-size: 13px;")
        layout.addWidget(sub)

        link = QLabel('<a style="color:%s; text-decoration:none;" '
                      'href="https://console.groq.com/keys">Obtener una gratis en '
                      'console.groq.com/keys →</a>' % accent)
        link.setOpenExternalLinks(True)
        link.setStyleSheet("font-size: 13px;")
        layout.addWidget(link)
        layout.addSpacing(4)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("gsk_...")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.returnPressed.connect(self._save_key)
        layout.addWidget(self.key_input)

        save_btn = QPushButton("Guardar y continuar")
        save_btn.setObjectName("primary")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setMinimumHeight(38)
        save_btn.clicked.connect(self._save_key)
        layout.addWidget(save_btn)

        self.setLayout(layout)

    def _save_key(self):
        key = self.key_input.text().strip()
        if not key.startswith("gsk_") or len(key) < 20:
            QMessageBox.warning(self, "Error", "La clave debe comenzar con 'gsk_' y tener al menos 20 caracteres.")
            return

        # Primary store: macOS Keychain (matches how the Hub saves keys).
        try:
            from core.secrets import set_key
            set_key("GROQ_API_KEY", key)
        except Exception:
            pass
        # Fallback/interop: also write .env, but 0600 (owner-only) not the
        # default world-readable 0644, so the key isn't readable by other users.
        env_path = os.path.join(APP_DATA_DIR, ".env")
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        with open(env_path, "w") as f:
            f.write(f"GROQ_API_KEY={key}\n")
        try:
            os.chmod(env_path, 0o600)
        except OSError:
            pass

        os.environ["GROQ_API_KEY"] = key
        self.accept()


def _is_launch_at_login() -> bool:
    return os.path.exists(_PLIST_PATH)


def _set_launch_at_login(enabled: bool):
    if enabled:
        if getattr(sys, "frozen", False):
            exe = sys.executable
        else:
            exe = os.path.abspath(sys.argv[0])

        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LAUNCH_AGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>"""
        os.makedirs(os.path.dirname(_PLIST_PATH), exist_ok=True)
        with open(_PLIST_PATH, "w") as f:
            f.write(plist)
        subprocess.run(["launchctl", "load", _PLIST_PATH], capture_output=True)
    else:
        if os.path.exists(_PLIST_PATH):
            subprocess.run(["launchctl", "unload", _PLIST_PATH], capture_output=True)
            os.remove(_PLIST_PATH)


def _setup_tray(app: QApplication, open_hub) -> QSystemTrayIcon:
    pixmap = QPixmap(LOGO_PATH)
    if pixmap.isNull():
        icon = QIcon()
    else:
        icon = QIcon(pixmap.scaled(22, 22, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    tray = QSystemTrayIcon(icon, app)

    menu = QMenu()

    status = QAction("SFlow — Activo", menu)
    status.setEnabled(False)
    menu.addAction(status)
    menu.addSeparator()

    hub_action = QAction("Abrir Hub  (⌘⇧H)", menu)
    hub_action.triggered.connect(open_hub)
    menu.addAction(hub_action)
    menu.addSeparator()

    login_action = QAction("Iniciar con macOS", menu)
    login_action.setCheckable(True)
    login_action.setChecked(_is_launch_at_login())
    login_action.toggled.connect(_set_launch_at_login)
    menu.addAction(login_action)
    menu.addSeparator()

    relaunch_action = QAction("Reiniciar SFlow", menu)
    relaunch_action.triggered.connect(relaunch_app)
    menu.addAction(relaunch_action)

    quit_action = QAction("Salir", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    # Also open hub on single left-click on the tray icon
    def _activate(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            open_hub()
    tray.activated.connect(_activate)

    tray.setContextMenu(menu)
    tray.setToolTip("SFlow — Voice to Text")
    tray.show()
    return tray


class SFlowApp(QObject):
    """Main controller. Wires hotkey -> recorder -> transcriber -> clipboard,
    plus Command Mode side-channel."""

    transcription_done = pyqtSignal(str, float, str)  # text, duration, model_id
    transcription_error = pyqtSignal(str)
    command_done = pyqtSignal(str)
    command_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.recorder = AudioRecorder()
        self.transcriber = Transcriber()
        # Warm-load del modelo local activo en background: deja el modelo residente
        # para que el PRIMER dictado ya salga en latencia warm (no cold-start).
        threading.Thread(target=self.transcriber.warm_active, daemon=True).start()
        self.groq_raw = GroqTranscriber()  # raw STT for command mode (no LLM cleanup)
        self.command = CommandModeHandler()
        self.transform = TransformHandler()
        self.db = TranscriptionDB()
        self.hotkey = HotkeyListener()
        self.pill = PillWidget()
        self.red_dot = RedDotIndicator()
        self.hub = HubWindow(self.db)

        self._selected_text_snapshot = ""
        self._last_text: str = ""  # For "paste last transcript" hotkey

        self.pill.visualizer.set_audio_queue(self.recorder.audio_queue)

        # Signals — all QueuedConnection (pynput emits from its own thread)
        self.hotkey.pressed.connect(self._on_hotkey_pressed, Qt.ConnectionType.QueuedConnection)
        self.hotkey.released.connect(self._on_hotkey_released, Qt.ConnectionType.QueuedConnection)
        self.hotkey.transform_triggered.connect(self._on_transform, Qt.ConnectionType.QueuedConnection)
        self.hotkey.hands_free_started.connect(self.red_dot.start, Qt.ConnectionType.QueuedConnection)
        self.hotkey.hands_free_stopped.connect(self.red_dot.stop, Qt.ConnectionType.QueuedConnection)
        # Command Mode (Ctrl+Shift hold) + Cmd+Shift+H (Hub) + Cmd+Ctrl+V (paste last)
        self.hotkey.command_pressed.connect(self._on_command_pressed, Qt.ConnectionType.QueuedConnection)
        self.hotkey.command_released.connect(self._on_command_released, Qt.ConnectionType.QueuedConnection)
        self.hotkey.hub_requested.connect(self._on_hub_requested, Qt.ConnectionType.QueuedConnection)
        self.hotkey.paste_last_requested.connect(self._on_paste_last, Qt.ConnectionType.QueuedConnection)

        self.transcription_done.connect(self._on_transcription_done, Qt.ConnectionType.QueuedConnection)
        self.transcription_error.connect(self._on_transcription_error, Qt.ConnectionType.QueuedConnection)
        self.command_done.connect(self._on_command_done, Qt.ConnectionType.QueuedConnection)
        self.command_error.connect(self._on_transcription_error, Qt.ConnectionType.QueuedConnection)

    def start(self):
        self.hotkey.start()
        # Do NOT force-show the pill at startup: it stays hidden while idle and
        # fades in on the first dictation (set_state binds visibility to state).
        self.pill.set_state(PillWidget.STATE_IDLE)
        # Privacy/retention: delete retry-WAVs older than 7 days on each launch
        # (off-thread so a slow disk never delays startup).
        threading.Thread(target=self._prune_old_audio, daemon=True).start()

    def _prune_old_audio(self):
        try:
            for p in self.db.prune_old_audio_paths(days=7):
                try:
                    os.remove(p)
                except OSError:
                    pass
        except Exception as e:
            log_exc("audio prune failed", e)

    def shutdown(self):
        """Best-effort teardown on quit: stop the global hotkey listener and any
        in-flight audio stream so PortAudio/pynput close cleanly."""
        try:
            self.hotkey.stop()
        except Exception:
            pass
        try:
            self.recorder.stop()
        except Exception:
            pass

    # ------- Regular transcription flow -------
    @pyqtSlot()
    def _on_hotkey_pressed(self):
        try:
            save_frontmost_app()
            try:
                from core.context import detect_active_app
                self._dictation_app = detect_active_app()[1] or None
            except Exception:
                self._dictation_app = None
            self.recorder.start()
            self.pill.set_state(PillWidget.STATE_RECORDING)
        except Exception as e:
            log_exc("hotkey_pressed crashed (suppressed)", e)
            try:
                self.pill.set_state(PillWidget.STATE_ERROR)
            except Exception:
                pass

    @pyqtSlot()
    def _on_hotkey_released(self):
        try:
            duration = self.recorder.stop()
            self.pill.set_state(PillWidget.STATE_PROCESSING)

            if duration < 0.3:
                self.pill.set_state(PillWidget.STATE_IDLE)
                return

            wav_buffer = self.recorder.get_wav_buffer()
            recording_duration = self.recorder.get_duration()

            # Persist WAV so the user can re-transcribe from the Hub later
            audio_path = None
            if get_setting("save_audio_for_retry", True):
                import uuid
                audio_path = os.path.join(AUDIO_DIR, f"{uuid.uuid4().hex}.wav")
                try:
                    self.recorder.save_wav_to(audio_path)
                except Exception as e:
                    print(f"audio save failed: {e}")
                    audio_path = None

            threading.Thread(
                target=self._transcribe_worker,
                args=(wav_buffer, recording_duration, audio_path),
                daemon=True,
            ).start()
        except Exception as e:
            log_exc("hotkey_released crashed (suppressed)", e)
            try:
                self.pill.set_state(PillWidget.STATE_ERROR)
            except Exception:
                pass

    def _transcribe_worker(self, wav_buffer, duration, audio_path=None):
        log(f"transcribe start: duration={duration:.2f}s, audio_path={audio_path}")
        try:
            text, model_id = self.transcriber.transcribe(wav_buffer)
            # Privacy: never log transcript CONTENT — dictations may contain
            # passwords, 2FA codes, private messages. Log length only.
            log(f"transcribe ok: model={model_id}, chars={len(text) if text else 0}")
            if text:
                self._pending_audio_path = audio_path
                self.transcription_done.emit(text, duration, model_id)
            else:
                log("transcribe returned empty text", level="WARN")
                self.transcription_error.emit("No speech detected")
        except Exception as e:
            log_exc("transcribe FAILED", e)
            self.transcription_error.emit(str(e))

    @pyqtSlot(str, float, str)
    def _on_transcription_done(self, text: str, duration: float, model_id: str):
        log(f"transcription_done: chars={len(text)}")
        final_text = text
        try:
            paste_text(final_text)
            log("paste ok")
        except Exception as e:
            log_exc("paste FAILED", e)
        self._last_text = final_text
        audio_path = getattr(self, "_pending_audio_path", None)
        self._pending_audio_path = None
        try:
            self.db.insert(
                text=final_text, duration_seconds=duration,
                model=model_id, audio_path=audio_path,
                app=getattr(self, "_dictation_app", None),
            )
        except Exception as e:
            log_exc("db.insert FAILED", e)
        self.pill.set_state(
            PillWidget.STATE_DONE_CLOUD if _was_cloud_fallback(model_id) else PillWidget.STATE_DONE
        )

    @pyqtSlot()
    def _on_hub_requested(self):
        # Temporarily activate the app so the Hub can receive keyboard focus
        # even though we're in accessory (menu-bar-only) policy.
        try:
            import AppKit
            AppKit.NSApp.activateIgnoringOtherApps_(True)
        except Exception:
            pass
        self.hub.show()
        self.hub.raise_()
        self.hub.activateWindow()

    @pyqtSlot()
    def _on_paste_last(self):
        # Prefer the in-memory last; fall back to DB most recent
        text = self._last_text
        if not text:
            rows = self.db.get_recent(limit=1)
            if rows:
                text = rows[0].get("text") or ""
        if text:
            paste_last_transcript(text)

    @pyqtSlot(int)
    def _on_transform(self, index: int):
        """Option+N — transform selected text via Llama with the Nth custom prompt."""
        save_frontmost_app()
        selection = copy_selection()
        if not selection:
            self.pill.set_state(PillWidget.STATE_ERROR)
            return
        self.pill.set_state(PillWidget.STATE_PROCESSING)

        def worker():
            try:
                result = self.transform.run(index, selection)
                self.command_done.emit(result)
            except Exception as e:
                self.command_error.emit(str(e))
        threading.Thread(target=worker, daemon=True).start()

    @pyqtSlot(str)
    def _on_transcription_error(self, error: str):
        log(f"ERROR state: {error}", level="ERROR")
        self.pill.set_state(PillWidget.STATE_ERROR)

    # ------- Command Mode flow -------
    @pyqtSlot()
    def _on_command_pressed(self):
        save_frontmost_app()
        # Snapshot selection BEFORE we grab focus for recording
        self._selected_text_snapshot = copy_selection()
        self.recorder.start()
        self.pill.set_state(PillWidget.STATE_RECORDING)

    @pyqtSlot()
    def _on_command_released(self):
        duration = self.recorder.stop()
        self.pill.set_state(PillWidget.STATE_PROCESSING)

        if duration < 0.3:
            self.pill.set_state(PillWidget.STATE_IDLE)
            self._selected_text_snapshot = ""
            return

        wav_buffer = self.recorder.get_wav_buffer()
        selection = self._selected_text_snapshot
        self._selected_text_snapshot = ""
        threading.Thread(
            target=self._command_worker,
            args=(wav_buffer, selection, duration),
            daemon=True,
        ).start()

    def _command_worker(self, wav_buffer, selection, duration):
        try:
            # Command Mode always uses Groq (fast cloud STT) — bypass local backend
            voice = self.groq_raw.transcribe(wav_buffer)
            if not voice:
                self.command_error.emit("No voice command detected")
                return
            result = self.command.transform(voice, selection)
            # Persist both voice command and result for history
            try:
                self.db.insert(
                    text=f"[CMD] {voice} → {result[:200]}",
                    duration_seconds=duration,
                    model="command-mode",
                )
            except Exception:
                pass
            self.command_done.emit(result)
        except Exception as e:
            self.command_error.emit(str(e))

    @pyqtSlot(str)
    def _on_command_done(self, result: str):
        paste_text(result)
        self._last_text = result
        self.pill.set_state(PillWidget.STATE_DONE)


def _install_safe_excepthook():
    """PyQt6 6.5+ aborts the process when a Qt slot raises an unhandled
    exception (QMessageLogger::fatal). Install a hook that logs instead of
    killing the app — defensive last-resort safety net."""
    def _hook(exc_type, exc_value, exc_tb):
        try:
            tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            log(f"unhandled exception (suppressed by excepthook)\n{tb}", level="ERROR")
        except Exception:
            pass
    sys.excepthook = _hook
    try:
        threading.excepthook = lambda args: _hook(args.exc_type, args.exc_value, args.exc_traceback)
    except Exception:
        pass


def _selftest_stt():
    """Prueba los motores STT DENTRO del binario (frozen o dev). Sin GUI.
    Uso: SFlow --selftest-stt   ó   python main.py --selftest-stt
    Genera un tono en memoria y corre cada motor local; imprime PASS/FAIL."""
    import io, wave, time
    import numpy as np
    from config import STT_MODELS, set_setting, get_setting
    from core.transcriber import Transcriber
    _orig_model = get_setting("stt_model", "whisper-turbo-local")
    sr = 16000
    t = np.linspace(0, 1.2, int(sr * 1.2), False)
    tone = (0.1 * np.sin(2 * np.pi * 200 * t) * 32767).astype("int16")
    def wav():
        b = io.BytesIO()
        with wave.open(b, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(tone.tobytes())
        b.seek(0); return b
    frozen = getattr(sys, "frozen", False)
    print(f"[selftest] frozen={frozen}")
    # Diagnostico: disponibilidad real de cada motor local (import de MLX)
    from core.transcriber_local import LocalTranscriber
    from core.transcriber_parakeet import ParakeetTranscriber
    _wl = LocalTranscriber(); _pk = ParakeetTranscriber()
    print(f"[selftest] whisper available={_wl.available} err={getattr(_wl,'_import_error',None)}")
    print(f"[selftest] parakeet available={_pk.available} err={getattr(_pk,'_import_error',None)}")
    ok = True
    for m in STT_MODELS:
        if not m["local"]:
            continue
        set_setting("stt_model", m["id"])
        tr = Transcriber()
        try:
            t0 = time.perf_counter(); tr.warm_active(); warm = time.perf_counter() - t0
            t0 = time.perf_counter(); _txt, mid = tr.transcribe(wav()); lat = time.perf_counter() - t0
            print(f"[selftest] {m['id']:20} PASS  load={warm:.1f}s infer={lat*1000:.0f}ms model={mid}")
        except Exception as e:
            ok = False
            print(f"[selftest] {m['id']:20} FAIL  {type(e).__name__}: {e}")
    set_setting("stt_model", _orig_model)  # restaura el ajuste real del usuario
    print("[selftest] RESULT:", "ALL_PASS" if ok else "SOME_FAIL")
    sys.exit(0 if ok else 1)


def main():
    _install_safe_excepthook()

    if "--selftest-stt" in sys.argv:
        _selftest_stt()
        return

    app = QApplication(sys.argv)
    app.setApplicationName("SFlow")
    app.setQuitOnLastWindowClosed(False)

    # Global design system (fonts + light/dark QSS). Re-apply live when the
    # macOS appearance changes and the user is on "auto".
    apply_theme(app)

    def _on_system_scheme_changed(_cs=None):
        if get_setting("theme", "auto") == "auto":
            apply_theme(app)
    try:
        app.styleHints().colorSchemeChanged.connect(_on_system_scheme_changed)
    except Exception:
        pass

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        dialog = FirstRunDialog()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)

    try:
        import AppKit
        AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    except Exception:
        pass

    _ensure_accessibility()

    sflow = SFlowApp()
    sflow.start()
    app.aboutToQuit.connect(sflow.shutdown)

    def open_hub():
        try:
            import AppKit
            AppKit.NSApp.activateIgnoringOtherApps_(True)
        except Exception:
            pass
        sflow.hub.show()
        sflow.hub.raise_()
        sflow.hub.activateWindow()

    tray = _setup_tray(app, open_hub)  # noqa: F841

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
