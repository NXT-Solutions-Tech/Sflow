"""El pegado no debe robar foco, ni colgarse, ni perder selecciones.

Tres regresiones reales cubiertas aquí:

1. paste_text() llamaba _restore_focus() SIEMPRE. Con el backend keystroke eso
   es un app-switch redundante (el flash) y, si el usuario se cambió de ventana
   durante la transcripción (~950ms), le arrancaba el foco de vuelta y escribía
   en la app vieja. Los CGEvent van a quien tenga el foco: no hace falta.
2. _cmd_v() era el único subprocess sin timeout + check=True → un osascript
   colgado colgaba el hilo llamante para siempre.
3. copy_selection() detectaba la selección comparando el CONTENIDO del
   clipboard. Copiar un texto, seleccionar ese mismo texto y hablarle daba
   after == before → "no hay selección".

Todo esto tiene efectos nativos (CGEvent, NSPasteboard, osascript), así que
aquí se stubea agresivamente y se verifica QUIÉN se llamó.
"""
import subprocess
import sys

import pytest

import config
from core import command_mode, paste


@pytest.fixture
def calls():
    return []


@pytest.fixture
def no_threads(monkeypatch):
    """copy_selection/_paste_via_clipboard restauran el clipboard en un hilo
    diferido que escribe en el NSPasteboard REAL. En tests eso pisaría el
    clipboard del usuario (y encima tras el teardown del monkeypatch), así que
    interceptamos el `import threading` que ambos hacen dentro de la función."""
    scheduled = []

    class _FakeThread:
        def __init__(self, target=None, daemon=None, **_kw):
            self._target = target
            scheduled.append(target)

        def start(self):
            pass  # nunca corremos el restore diferido

    fake = type(sys)("threading")
    fake.Thread = _FakeThread
    monkeypatch.setitem(sys.modules, "threading", fake)
    return scheduled


# ---------- (a) keystroke NO restaura foco ----------
def test_keystroke_backend_never_restores_focus(monkeypatch, calls):
    """La regresión que importa: el path por defecto no debe tocar el foco."""
    config.set_setting("paste_backend", "keystroke")
    config.set_setting("streaming_paste_enabled", False)

    monkeypatch.setattr(paste, "_restore_focus", lambda: calls.append("restore"))
    monkeypatch.setattr(paste, "_paste_via_clipboard", lambda t: calls.append("clipboard"))
    monkeypatch.setattr(paste, "_type_via_cgevent", lambda t: calls.append(f"type:{t}") or True)

    paste.paste_text("hola mundo")

    assert calls == ["type:hola mundo"]
    assert "restore" not in calls


def test_streaming_keystroke_never_restores_focus(monkeypatch, calls):
    config.set_setting("paste_backend", "keystroke")
    config.set_setting("streaming_paste_enabled", True)

    monkeypatch.setattr(paste, "_restore_focus", lambda: calls.append("restore"))
    monkeypatch.setattr(paste.time, "sleep", lambda _s: None)
    monkeypatch.setattr(paste, "_type_via_cgevent", lambda t: calls.append(f"type:{t}") or True)

    paste.paste_text("una frase bastante larga para superar el umbral de streaming")

    assert "restore" not in calls
    assert "".join(c.removeprefix("type:") for c in calls) == (
        "una frase bastante larga para superar el umbral de streaming"
    )


# ---------- (b) el path clipboard SÍ restaura foco ----------
def test_clipboard_backend_routes_through_the_clipboard_path(monkeypatch, calls):
    config.set_setting("paste_backend", "clipboard")

    monkeypatch.setattr(paste, "_restore_focus", lambda: calls.append("restore"))
    monkeypatch.setattr(paste, "_type_via_cgevent", lambda t: calls.append("type") or True)
    monkeypatch.setattr(paste, "_paste_via_clipboard", lambda t: calls.append(f"clipboard:{t}"))

    paste.paste_text("hola")

    assert calls == ["clipboard:hola"]
    assert "type" not in calls


def test_paste_via_clipboard_restores_focus_before_pasting(monkeypatch, calls, no_threads):
    """Cmd+V va vía System Events a la app ACTIVA: sin restore pega en SFlow."""
    monkeypatch.setattr(paste, "_clipboard_read", lambda: "previo")
    monkeypatch.setattr(paste, "_clipboard_write", lambda t: calls.append(f"write:{t}"))
    monkeypatch.setattr(paste, "_restore_focus", lambda: calls.append("restore"))
    monkeypatch.setattr(paste, "_cmd_v", lambda: calls.append("cmd_v") or True)

    paste._paste_via_clipboard("hola")

    assert calls.index("restore") < calls.index("cmd_v"), "restore debe ir ANTES del Cmd+V"


def test_cgevent_failure_falls_back_to_clipboard_and_restores_once(monkeypatch, calls):
    """Fallback keystroke→clipboard: el restore debe ocurrir, y una sola vez."""
    config.set_setting("paste_backend", "keystroke")
    config.set_setting("streaming_paste_enabled", False)

    monkeypatch.setattr(paste, "_restore_focus", lambda: calls.append("restore"))
    monkeypatch.setattr(paste, "_type_via_cgevent", lambda t: calls.append("type") and False)

    def _fake_clipboard(t):
        calls.append("clipboard")
        paste._restore_focus()
    monkeypatch.setattr(paste, "_paste_via_clipboard", _fake_clipboard)

    paste.paste_text("hola")

    assert calls == ["type", "clipboard", "restore"]
    assert calls.count("restore") == 1


# ---------- paste_text propaga el exito ----------
# El path clipboard reporta el fallo DEVOLVIENDO False (antes lanzaba, por el
# check=True sin timeout de _cmd_v). Si paste_text se come ese bool, main.py
# nunca ve el fallo y pinta el check verde sobre un pegado perdido.
def test_paste_text_reports_a_failed_clipboard_paste(monkeypatch):
    config.set_setting("paste_backend", "clipboard")
    monkeypatch.setattr(paste, "_paste_via_clipboard", lambda t: False)

    assert paste.paste_text("hola") is False


def test_paste_text_reports_success(monkeypatch):
    config.set_setting("paste_backend", "clipboard")
    monkeypatch.setattr(paste, "_paste_via_clipboard", lambda t: True)

    assert paste.paste_text("hola") is True


def test_paste_text_reports_a_failed_fallback(monkeypatch):
    """keystroke cae a clipboard y el clipboard tambien falla."""
    config.set_setting("paste_backend", "keystroke")
    config.set_setting("streaming_paste_enabled", False)
    monkeypatch.setattr(paste, "_type_via_cgevent", lambda t: False)
    monkeypatch.setattr(paste, "_paste_via_clipboard", lambda t: False)

    assert paste.paste_text("hola") is False


def test_paste_text_reports_a_failed_streaming_fallback(monkeypatch):
    config.set_setting("paste_backend", "keystroke")
    config.set_setting("streaming_paste_enabled", True)
    monkeypatch.setattr(paste, "_type_via_cgevent", lambda t: False)
    monkeypatch.setattr(paste, "_paste_via_clipboard", lambda t: False)

    assert paste.paste_text("x" * 50) is False


# ---------- (c) _cmd_v no puede colgarse ----------
def test_cmd_v_passes_a_timeout(monkeypatch):
    seen = {}

    def _fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(paste.subprocess, "run", _fake_run)

    assert paste._cmd_v() is True
    assert seen["kwargs"].get("timeout"), "sin timeout un osascript colgado cuelga el hilo"
    assert "osascript" in seen["cmd"][0]


def test_cmd_v_swallows_a_hung_osascript(monkeypatch):
    def _hang(cmd, **_kw):
        raise subprocess.TimeoutExpired(cmd, 2)
    monkeypatch.setattr(paste.subprocess, "run", _hang)

    assert paste._cmd_v() is False  # reporta el fallo, no propaga


def test_cmd_v_swallows_a_nonzero_exit(monkeypatch):
    def _fail(cmd, **_kw):
        raise subprocess.CalledProcessError(1, cmd)
    monkeypatch.setattr(paste.subprocess, "run", _fail)

    assert paste._cmd_v() is False


# ---------- (d) copy_selection vía changeCount ----------
@pytest.fixture
def stub_copy(monkeypatch):
    """Neutraliza el Cmd+C real y el sleep."""
    monkeypatch.setattr(command_mode.subprocess, "run",
                        lambda cmd, **_kw: subprocess.CompletedProcess(cmd, 0))
    monkeypatch.setattr(command_mode.time, "sleep", lambda _s: None)


def _clipboard_returns(monkeypatch, *values):
    seq = iter(values)
    monkeypatch.setattr(command_mode, "_read_clipboard", lambda: next(seq))


def test_selection_identical_to_the_clipboard_is_still_detected(
    monkeypatch, stub_copy, no_threads
):
    """El caso que fallaba: copiar un texto, seleccionar ESE MISMO texto y
    hablarle. after == before, pero changeCount subió → sí hubo selección."""
    _clipboard_returns(monkeypatch, "mismo texto", "mismo texto")
    counts = iter([7, 8])
    monkeypatch.setattr(command_mode, "_change_count", lambda: next(counts))

    assert command_mode.copy_selection() == "mismo texto"


def test_no_selection_reports_empty(monkeypatch, stub_copy, no_threads):
    """Cmd+C sin selección no escribe: changeCount no se mueve."""
    _clipboard_returns(monkeypatch, "algo copiado antes", "algo copiado antes")
    monkeypatch.setattr(command_mode, "_change_count", lambda: 7)

    assert command_mode.copy_selection() == ""


def test_new_selection_is_returned_and_clipboard_restore_scheduled(
    monkeypatch, stub_copy, no_threads
):
    _clipboard_returns(monkeypatch, "previo", "seleccionado")
    counts = iter([7, 8])
    monkeypatch.setattr(command_mode, "_change_count", lambda: next(counts))

    assert command_mode.copy_selection() == "seleccionado"
    assert no_threads, "debe programar la restauración del clipboard del usuario"


def test_falls_back_to_content_diff_without_pyobjc(monkeypatch, stub_copy, no_threads):
    """Sin PyObjC no hay changeCount: se degrada al viejo diff por contenido."""
    _clipboard_returns(monkeypatch, "previo", "seleccionado")
    monkeypatch.setattr(command_mode, "_change_count", lambda: None)

    assert command_mode.copy_selection() == "seleccionado"


def test_change_count_returns_none_when_appkit_is_missing(monkeypatch):
    def boom(*_a, **_k):
        raise ImportError("AppKit missing")
    monkeypatch.setattr("builtins.__import__", boom)
    assert command_mode._change_count() is None


def test_copy_selection_gives_up_when_cmd_c_fails(monkeypatch, no_threads):
    def _fail(cmd, **_kw):
        raise subprocess.TimeoutExpired(cmd, 1)
    monkeypatch.setattr(command_mode.subprocess, "run", _fail)
    monkeypatch.setattr(command_mode, "_read_clipboard", lambda: "previo")

    assert command_mode.copy_selection() == ""
