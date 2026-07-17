"""Trailing "dale enter" — the verbal action CLAUDE.md has always advertised and
that was never wired (the module existed with zero importers until now).

extract_actions is pure; the wiring in main._on_transcription_done is what these
guard: the suffix must never reach the app, and Enter must never fire on text
that failed to paste.
"""
import pytest
from PyQt6.QtCore import QObject

from core.dictation_actions import ACTION_PRESS_ENTER, extract_actions


def test_spanish_suffix_is_stripped_and_becomes_an_action():
    text, actions = extract_actions("manda el reporte dale enter")
    assert text == "manda el reporte"
    assert actions == [ACTION_PRESS_ENTER]


def test_english_suffix_is_stripped():
    text, actions = extract_actions("send the report press enter")
    assert text == "send the report"
    assert actions == [ACTION_PRESS_ENTER]


def test_suffix_with_trailing_punctuation():
    text, actions = extract_actions("listo, dale enter.")
    assert text == "listo"
    assert actions == [ACTION_PRESS_ENTER]


def test_plain_text_is_untouched():
    text, actions = extract_actions("hola que tal")
    assert text == "hola que tal"
    assert actions == []


def test_enter_mid_sentence_is_not_a_command():
    """Only a TRAILING command counts — otherwise dictating about the Enter key
    would silently lose words."""
    text, actions = extract_actions("dale enter y luego cierra")
    assert text == "dale enter y luego cierra"
    assert actions == []


def test_empty_text_is_safe():
    assert extract_actions("") == ("", [])


class _Pill:
    def __init__(self): self.state = None
    def set_state(self, s): self.state = s


def _wire(monkeypatch, paste_raises=False, paste_returns=True):
    """Drive main._on_transcription_done with everything native stubbed out.

    SFlowApp is a QObject: built via __new__ alone, every attribute access raises
    and _on_transcription_done's try/except swallows it — the assertions then pass
    against a slot that did nothing. QObject.__init__ is what makes these real.
    """
    import main

    performed, pasted, rows = [], [], []

    def _paste(t):
        pasted.append(t)
        if paste_raises:
            raise RuntimeError("accessibility revoked")
        return paste_returns

    monkeypatch.setattr(main, "paste_text", _paste)
    monkeypatch.setattr(main, "perform_actions", lambda a: performed.extend(a))
    monkeypatch.setattr(main, "_was_cloud_fallback", lambda _m: False)
    # The slot logs and moves on if insert() throws; surface it instead.
    monkeypatch.setattr(main, "log_exc", lambda m, e: pytest.fail(f"{m}: {e!r}")
                        if "db.insert" in m else None)

    app = main.SFlowApp.__new__(main.SFlowApp)
    QObject.__init__(app)
    app.pill = _Pill()
    app.db = type("D", (), {"insert": lambda _s, **k: rows.append(k["text"])})()
    app._pending_audio_path = None
    app._dictation_app = None
    app.notify = lambda *_a, **_k: None
    return main, app, performed, pasted, rows


def test_enter_fires_after_a_successful_paste(monkeypatch):
    main, app, performed, pasted, _ = _wire(monkeypatch)

    main.SFlowApp._on_transcription_done(app, "manda el correo dale enter", 1.0, "m")

    assert pasted == ["manda el correo"]   # the command never reaches the app
    assert performed == [ACTION_PRESS_ENTER]


def test_enter_does_not_fire_when_the_paste_failed(monkeypatch):
    """Pressing Enter after a failed paste would send an empty message — the
    exact wrong moment to hit send."""
    main, app, performed, _, _ = _wire(monkeypatch, paste_raises=True)

    main.SFlowApp._on_transcription_done(app, "manda el correo dale enter", 1.0, "m")

    assert performed == []
    assert app.pill.state == main.PillWidget.STATE_ERROR


def test_a_paste_that_returns_false_is_still_a_failure(monkeypatch):
    """The clipboard path signals failure by RETURNING False, not by raising.
    Treating a bare call as success flashes a check over a lost paste."""
    main, app, performed, _, _ = _wire(monkeypatch, paste_returns=False)

    main.SFlowApp._on_transcription_done(app, "manda el correo dale enter", 1.0, "m")

    assert app.pill.state == main.PillWidget.STATE_ERROR
    assert performed == []   # and Enter must not fire either


def test_history_stores_the_cleaned_text(monkeypatch):
    """"dale enter" is an instruction, not something to keep in history."""
    main, app, _, _, rows = _wire(monkeypatch)

    main.SFlowApp._on_transcription_done(app, "nota rapida dale enter", 1.0, "m")

    assert rows == ["nota rapida"]
