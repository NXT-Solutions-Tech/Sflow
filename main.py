#!/usr/bin/env python3
"""SFlow — Voice-to-text desktop tool. Local Whisper Turbo / Parakeet (offline,
default) with Groq cloud fallback, LLM cleanup, per-app tone, Command Mode,
and a light+dark native Hub."""

import os
import sys
import signal
import subprocess
import threading
import time
import traceback
import multiprocessing

# CRITICO en un .app congelado (PyInstaller): numba/librosa (motores locales)
# lanzan procesos con multiprocessing (start method "spawn" en macOS), que
# re-ejecutan el binario. Sin freeze_support(), cada worker cae en main() y
# ABRE OTRA VENTANA (pill). freeze_support() intercepta al worker y lo hace
# salir antes de llegar a main(). Debe ser lo PRIMERO que corre.
multiprocessing.freeze_support()
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon, QPixmap, QAction

from ui.pill_widget import PillWidget
from ui.hub_window import HubWindow
from ui.red_dot_indicator import RedDotIndicator
from core.recorder import AudioRecorder
from core.transcriber import Transcriber
from core.hotkey import HotkeyListener
from core.paste import paste_text, paste_last_transcript, save_frontmost_app
from core.dictation_actions import extract_actions, perform_actions
from core.command_mode import CommandModeHandler, copy_selection
from core.transform import TransformHandler
from core.relaunch import relaunch_app
from core.logger import log, log_exc
from core import error_messages, onboarding, permissions, sounds
from core.secrets import get_key
from db.database import TranscriptionDB
from config import (
    LOGO_PATH, AUDIO_DIR, RECORDING_CAP_SECONDS, get_setting, set_setting, get_stt_model,
)
from ui import theme


def _discard_audio(path: str | None):
    """Unlink a retry-WAV whose dictation never reached the DB.

    The WAV is written at hotkey-release, before we know the transcription will
    land a row. Every path that ends without an insert MUST come through here or
    the file stays on disk forever: prune_old_audio_paths only walks rows, so an
    unreferenced WAV is invisible to it.
    """
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


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


def _run_onboarding_if_needed():
    """Show the guided wizard on first run, or when a permission has been
    revoked since.

    Replaces the old reactive _ensure_accessibility(), which only ever noticed
    Accessibility (never Input Monitoring, the one pynput needs), asked for the
    API key the default setup doesn't need, and — worst — returned True when its
    import failed, so a broken probe was indistinguishable from a granted
    permission.

    The revocation path matters on macOS: an ad-hoc rebuild changes the binary
    hash and TCC silently drops Accessibility, so the next dictation pastes
    nothing. plan_steps() narrows that to just the broken step.
    """
    perms = permissions.snapshot()
    seen = get_setting("onboarding_seen_version", 0)
    if not onboarding.needs_onboarding(seen, perms):
        return
    if not onboarding.should_prompt_again(time.time(), get_setting("onboarding_snooze_until", 0)):
        return

    key_required = onboarding.api_key_required(
        bool(get_stt_model().get("local")),
        get_setting("auto_cleanup_level", "none"),
    )
    # Keychain-first: os.getenv alone would re-prompt users who stored their key
    # there, which is where the app itself puts it.
    key_present = bool(get_key("GROQ_API_KEY"))

    # Offer the optional Whisper-Turbo download on first run only, and only if the
    # active local model isn't already present. Never on the permission-rescue
    # path — a revoked permission shouldn't turn into a download upsell.
    offer_model = False
    try:
        first_run = (seen or 0) < onboarding.ONBOARDING_VERSION
        active = get_stt_model()
        if first_run and active.get("local"):
            from core.models import ModelManager
            offer_model = not ModelManager().is_available(active.get("model", ""))
    except Exception:
        offer_model = False

    steps = onboarding.plan_steps(perms, key_required, key_present,
                                  offer_model_download=offer_model)
    try:
        from ui.onboarding_wizard import OnboardingWizard
        OnboardingWizard(steps, key_required=key_required).exec()
    except Exception as e:
        # Onboarding is a helper, never a gate: if it breaks, the app still runs.
        log_exc("onboarding wizard failed (suppressed)", e)
        return
    # Written even when steps were skipped — the user has seen the flow, and
    # re-showing it every launch would be nagging, not helping.
    set_setting("onboarding_seen_version", onboarding.ONBOARDING_VERSION)


_LAUNCH_AGENT_LABEL = "so.saasfactory.sflow"
_PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{_LAUNCH_AGENT_LABEL}.plist")


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

    # audio_path travels WITH the result, not in an attribute: the worker runs off
    # the main thread while the slot is queued, so two overlapping dictations used
    # to cross wires — row A ending up pointing at B's WAV (and "Re-transcribir"
    # then overwriting A's text with B's audio).
    transcription_done = pyqtSignal(str, float, str, str)  # text, duration, model_id, audio_path
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
        self.command = CommandModeHandler()
        self.transform = TransformHandler()
        self.db = TranscriptionDB()
        self.hotkey = HotkeyListener()
        self.pill = PillWidget()
        self.red_dot = RedDotIndicator()
        self.hub = HubWindow(self.db)

        self._selected_text_snapshot = ""
        self._last_text: str = ""  # For "paste last transcript" hotkey
        self._tray: QSystemTrayIcon | None = None
        self._last_notify_code = ""
        self._last_notify_ts = 0.0

        # Hands-free runs unattended until a second Ctrl tap. Cap it: this
        # single-shot timer is armed when hands-free starts and disarmed when it
        # stops normally; if it fires, we auto-stop and toast.
        self._cap_timer = QTimer(self)
        self._cap_timer.setSingleShot(True)
        self._cap_timer.timeout.connect(self._on_recording_cap)

        self.pill.visualizer.set_audio_queue(self.recorder.audio_queue)

        # Signals — all QueuedConnection (pynput emits from its own thread)
        self.hotkey.pressed.connect(self._on_hotkey_pressed, Qt.ConnectionType.QueuedConnection)
        self.hotkey.released.connect(self._on_hotkey_released, Qt.ConnectionType.QueuedConnection)
        self.hotkey.transform_triggered.connect(self._on_transform, Qt.ConnectionType.QueuedConnection)
        self.hotkey.hands_free_started.connect(self.red_dot.start, Qt.ConnectionType.QueuedConnection)
        self.hotkey.hands_free_stopped.connect(self.red_dot.stop, Qt.ConnectionType.QueuedConnection)
        # Arm/disarm the recording cap alongside the red-dot lifecycle.
        self.hotkey.hands_free_started.connect(self._arm_cap, Qt.ConnectionType.QueuedConnection)
        self.hotkey.hands_free_stopped.connect(self._disarm_cap, Qt.ConnectionType.QueuedConnection)
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
                _discard_audio(p)
        except Exception as e:
            log_exc("audio prune failed", e)
        # Second pass, by mtime: catches WAVs no row references (dictations that
        # died before the insert). Runs after the row-driven prune so the ones it
        # just un-referenced are already gone.
        try:
            orphans = self.db.prune_orphan_audio_files(AUDIO_DIR, days=7)
            for p in orphans:
                _discard_audio(p)
            if orphans:
                log(f"pruned {len(orphans)} orphan WAV(s)")
        except Exception as e:
            log_exc("orphan audio prune failed", e)

    def set_tray(self, tray: QSystemTrayIcon):
        """The tray icon is the delivery vehicle for error toasts. It's built
        after SFlowApp, so it gets handed back here."""
        self._tray = tray

    def notify(self, toast):
        """Surface an error as a system notification.

        Strictly additive: the pill's ERROR state is the guaranteed feedback, so
        nothing here may affect control flow. Notifications can be silently
        dropped by macOS (Do Not Disturb, unsigned dev builds) and that must
        never turn into a crash or a swallowed failure.
        """
        try:
            if self._tray is None or not QSystemTrayIcon.supportsMessages():
                return
            now = time.time()
            if not error_messages.should_notify(
                toast.code, self._last_notify_code, self._last_notify_ts, now
            ):
                return
            self._last_notify_code = toast.code
            self._last_notify_ts = now
            self._tray.showMessage(
                toast.title, toast.body,
                QSystemTrayIcon.MessageIcon.Warning, 4000,
            )
        except Exception as e:
            log_exc("notify failed (suppressed)", e)

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
            sounds.play_start()
            self.pill.set_state(PillWidget.STATE_RECORDING)
        except Exception as e:
            log_exc("hotkey_pressed crashed (suppressed)", e)
            try:
                self.pill.set_state(PillWidget.STATE_ERROR)
            except Exception:
                pass

    @pyqtSlot()
    def _on_hotkey_released(self):
        # Bound outside the try: if anything below throws once the WAV is on disk,
        # the handler still has to discard it or it outlives every reference.
        audio_path = None
        self._cap_timer.stop()  # a normal stop disarms the hands-free cap
        try:
            duration = self.recorder.stop()
            self.pill.set_state(PillWidget.STATE_PROCESSING)

            if duration < 0.3:
                self.pill.set_state(PillWidget.STATE_IDLE)
                return

            wav_buffer = self.recorder.get_wav_buffer()
            recording_duration = self.recorder.get_duration()

            # Persist WAV so the user can re-transcribe from the Hub later
            if get_setting("save_audio_for_retry", True):
                import uuid
                audio_path = os.path.join(AUDIO_DIR, f"{uuid.uuid4().hex}.wav")
                try:
                    self.recorder.save_wav_to(audio_path)
                except Exception as e:
                    log_exc("audio save failed", e)
                    audio_path = None

            threading.Thread(
                target=self._transcribe_worker,
                args=(wav_buffer, recording_duration, audio_path),
                daemon=True,
            ).start()
            # Handed off: the worker owns the file from here.
            audio_path = None
        except Exception as e:
            _discard_audio(audio_path)
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
                self.transcription_done.emit(text, duration, model_id, audio_path or "")
            else:
                log("transcribe returned empty text", level="WARN")
                _discard_audio(audio_path)
                self.transcription_error.emit(error_messages.CODE_SILENCE)
        except Exception as e:
            # The raw exception stays in the log; the UI gets a code it can
            # turn into words the user can act on.
            log_exc("transcribe FAILED", e)
            _discard_audio(audio_path)
            self.transcription_error.emit(error_messages.classify_exception(e))

    @pyqtSlot(str, float, str, str)
    def _on_transcription_done(self, text: str, duration: float, model_id: str,
                               audio_path: str = ""):
        log(f"transcription_done: chars={len(text)}")
        # A trailing "dale enter" is an instruction, not dictation: strip it
        # before it reaches the app, the history or the clipboard.
        final_text, actions = extract_actions(text)
        try:
            # The clipboard path reports failure by returning False, not by
            # raising — a bare call here would flash a check over a lost paste.
            paste_ok = paste_text(final_text)
            log("paste ok" if paste_ok else "paste failed")
        except Exception as e:
            paste_ok = False
            log_exc("paste FAILED", e)
        self._last_text = final_text
        # Insert even when the paste failed: history is the recovery path the
        # "no se pudo pegar" toast points the user at.
        try:
            self.db.insert(
                text=final_text, duration_seconds=duration,
                model=model_id, audio_path=audio_path or None,
                app=getattr(self, "_dictation_app", None),
            )
        except Exception as e:
            log_exc("db.insert FAILED", e)
            # No row → nothing will ever reference this WAV again.
            _discard_audio(audio_path)
        if not paste_ok:
            # A checkmark here would claim the text landed somewhere it didn't.
            self.pill.set_state(PillWidget.STATE_ERROR)
            self.notify(error_messages.message_for(error_messages.CODE_PASTE_FAILED))
            return
        if actions:
            # Only after a successful paste: pressing Enter on text that never
            # landed would fire off an empty message.
            try:
                perform_actions(actions)
            except Exception as e:
                log_exc("dictation actions failed", e)
        sounds.play_done()  # only on a landed paste — never over a failure
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
            self.command_error.emit(error_messages.CODE_NO_SELECTION)
            return
        self.pill.set_state(PillWidget.STATE_PROCESSING)

        def worker():
            try:
                result = self.transform.run(index, selection)
                self.command_done.emit(result)
            except Exception as e:
                log_exc("transform FAILED", e)
                self.command_error.emit(error_messages.classify_exception(e))
        threading.Thread(target=worker, daemon=True).start()

    @pyqtSlot(str)
    def _on_transcription_error(self, code: str):
        """Both error signals land here. The payload is an error_messages code."""
        toast = error_messages.message_for(error_messages.classify_message(code))
        log(f"ERROR state: {toast.code}", level="ERROR")
        self.pill.set_state(PillWidget.STATE_ERROR)
        self.notify(toast)

    # ------- Hands-free recording cap -------
    @pyqtSlot()
    def _arm_cap(self):
        self._cap_timer.start(int(RECORDING_CAP_SECONDS * 1000))

    @pyqtSlot()
    def _disarm_cap(self):
        self._cap_timer.stop()

    @pyqtSlot()
    def _on_recording_cap(self):
        """Fired when hands-free ran past RECORDING_CAP_SECONDS. Stop cleanly,
        reset the listener (so the next Ctrl tap starts fresh), toast, and route
        through the normal release so what WAS captured still gets transcribed."""
        log(f"hands-free recording cap ({RECORDING_CAP_SECONDS}s) hit — auto-stopping", "WARN")
        try:
            self.red_dot.stop()
        except Exception:
            pass
        self.hotkey.force_reset()
        self.notify(error_messages.message_for(error_messages.CODE_RECORDING_CAPPED))
        self._on_hotkey_released()

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
            # Local-first raw STT: the audio stays on-device (only the LLM
            # transform below may reach the cloud, per the configured provider).
            voice = self.transcriber.transcribe_raw(wav_buffer)
            if not voice:
                self.command_error.emit(error_messages.CODE_SILENCE)
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
            log_exc("command mode FAILED", e)
            self.command_error.emit(error_messages.classify_exception(e))

    @pyqtSlot(str)
    def _on_command_done(self, result: str):
        self._last_text = result
        try:
            paste_text(result)
        except Exception as e:
            # Command Mode replaces a selection — claiming success when the
            # keystrokes never landed is worse here than anywhere else.
            log_exc("command paste FAILED", e)
            self.pill.set_state(PillWidget.STATE_ERROR)
            self.notify(error_messages.message_for(error_messages.CODE_PASTE_FAILED))
            return
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

    # Runs before the Accessory activation policy below, so the wizard can take
    # focus. It never exits: the app used to refuse to start without a Groq key
    # it doesn't need — the default engine transcribes on this Mac.
    _run_onboarding_if_needed()

    try:
        import AppKit
        AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    except Exception:
        pass

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

    sflow.set_tray(_setup_tray(app, open_hub))

    # The DB may have quarantined a corrupt history at construction (before the
    # tray existed to toast it). Surface it now that the tray is up.
    if getattr(sflow.db, "recovered_from_corruption", False):
        sflow.notify(error_messages.message_for(error_messages.CODE_DB_CORRUPT))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
