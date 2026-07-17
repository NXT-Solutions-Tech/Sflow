"""'Paste last transcript' (Cmd+Ctrl+V) must restore the user's clipboard.

The old clipboard branch did a bare _clipboard_write + _cmd_v, permanently
replacing whatever the user had copied. It now routes through
_paste_via_clipboard, which saves and restores it.
"""
import config
from core import paste


def test_clipboard_backend_routes_through_the_restoring_path(monkeypatch):
    config.set_setting("paste_backend", "clipboard")
    calls = []
    monkeypatch.setattr(paste, "_paste_via_clipboard", lambda t: calls.append(t) or True)
    monkeypatch.setattr(paste, "_clipboard_write", lambda t: calls.append(("raw_write", t)))
    monkeypatch.setattr(paste, "_cmd_v", lambda: calls.append("cmd_v") or True)

    paste.paste_last_transcript("hola")

    assert calls == ["hola"]  # restoring path only — never the clobbering raw write


def test_keystroke_fallback_uses_the_restoring_path(monkeypatch):
    config.set_setting("paste_backend", "keystroke")
    calls = []
    monkeypatch.setattr(paste, "_type_via_cgevent", lambda t: False)  # keystroke fails
    monkeypatch.setattr(paste, "_paste_via_clipboard", lambda t: calls.append(t) or True)
    monkeypatch.setattr(paste, "_clipboard_write", lambda t: calls.append(("raw_write", t)))

    paste.paste_last_transcript("hola")

    assert calls == ["hola"]


def test_keystroke_success_never_touches_the_clipboard(monkeypatch):
    config.set_setting("paste_backend", "keystroke")
    calls = []
    monkeypatch.setattr(paste, "_type_via_cgevent", lambda t: calls.append("type") or True)
    monkeypatch.setattr(paste, "_paste_via_clipboard", lambda t: calls.append("clipboard"))

    paste.paste_last_transcript("hola")

    assert calls == ["type"]


def test_empty_text_is_a_noop(monkeypatch):
    calls = []
    monkeypatch.setattr(paste, "_type_via_cgevent", lambda t: calls.append("x") or True)
    monkeypatch.setattr(paste, "_paste_via_clipboard", lambda t: calls.append("y"))

    paste.paste_last_transcript("")

    assert calls == []
