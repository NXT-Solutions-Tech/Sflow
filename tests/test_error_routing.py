"""A failed paste must never flash a success check.

_on_transcription_done used to call paste_text in a try/except that logged the
failure and then set STATE_DONE regardless — so when Accessibility was revoked
(which macOS does silently on every ad-hoc rebuild) the user saw a green
checkmark while the text went nowhere.

These drive the real slots with everything below them stubbed. SFlowApp itself
is never constructed: it builds a recorder, a DB, Qt widgets and warm-loads an
MLX model in __init__. The slots are plain methods, so binding them to a stand-in
exercises the actual logic without any of that.
"""
import pytest

import main
from core import error_messages as em


class FakePill:
    def __init__(self):
        self.states = []

    def set_state(self, state):
        self.states.append(state)


class FakeDB:
    def __init__(self):
        self.rows = []

    def insert(self, **kw):
        self.rows.append(kw)


class Stub:
    """Minimal stand-in carrying only what the slots under test touch."""

    def __init__(self):
        self.pill = FakePill()
        self.db = FakeDB()
        self.toasts = []
        self._last_text = ""
        self._pending_audio_path = None
        self._dictation_app = None

    def notify(self, toast):
        self.toasts.append(toast)


def _done(stub, text="hola", model_id="mlx-community/whisper-large-v3-turbo"):
    return main.SFlowApp._on_transcription_done(stub, text, 1.0, model_id)


@pytest.fixture
def stub():
    return Stub()


# ---------- paste failure ----------
def test_failed_paste_shows_error_not_a_checkmark(stub, monkeypatch):
    """The headline regression."""
    def boom(_text):
        raise RuntimeError("Accessibility denied")
    monkeypatch.setattr(main, "paste_text", boom)

    _done(stub)

    assert stub.pill.states == [main.PillWidget.STATE_ERROR]
    assert main.PillWidget.STATE_DONE not in stub.pill.states


def test_failed_paste_tells_the_user_where_the_text_went(stub, monkeypatch):
    monkeypatch.setattr(main, "paste_text", lambda _t: (_ for _ in ()).throw(RuntimeError("nope")))

    _done(stub)

    assert [t.code for t in stub.toasts] == [em.CODE_PASTE_FAILED]
    assert "historial" in stub.toasts[0].body.lower()


def test_transcript_is_still_saved_when_the_paste_fails(stub, monkeypatch):
    """History is the recovery path the toast points at — it must exist."""
    monkeypatch.setattr(main, "paste_text", lambda _t: (_ for _ in ()).throw(RuntimeError("nope")))

    _done(stub, text="texto importante")

    assert len(stub.db.rows) == 1
    assert stub.db.rows[0]["text"] == "texto importante"


# ---------- happy paths still work ----------
def test_successful_paste_still_shows_done(stub, monkeypatch):
    monkeypatch.setattr(main, "paste_text", lambda _t: None)
    monkeypatch.setattr(main, "_was_cloud_fallback", lambda _m: False)

    _done(stub)

    assert stub.pill.states == [main.PillWidget.STATE_DONE]
    assert stub.toasts == []


def test_cloud_fallback_state_survives_the_paste_check(stub, monkeypatch):
    """The amber cloud-fallback check must not be flattened back to DONE."""
    monkeypatch.setattr(main, "paste_text", lambda _t: None)
    monkeypatch.setattr(main, "_was_cloud_fallback", lambda _m: True)

    _done(stub)

    assert stub.pill.states == [main.PillWidget.STATE_DONE_CLOUD]


def test_a_failed_paste_beats_the_cloud_fallback_check(stub, monkeypatch):
    """Both conditions at once: "it didn't paste" is the more urgent truth."""
    monkeypatch.setattr(main, "paste_text", lambda _t: (_ for _ in ()).throw(RuntimeError("nope")))
    monkeypatch.setattr(main, "_was_cloud_fallback", lambda _m: True)

    _done(stub)

    assert stub.pill.states == [main.PillWidget.STATE_ERROR]


# ---------- the error slot ----------
def test_error_slot_turns_a_code_into_a_toast(stub):
    main.SFlowApp._on_transcription_error(stub, em.CODE_OFFLINE)

    assert stub.pill.states == [main.PillWidget.STATE_ERROR]
    assert stub.toasts[0].code == em.CODE_OFFLINE
    assert "internet" in stub.toasts[0].body.lower()


def test_error_slot_still_handles_a_raw_string(stub):
    """Defensive: classify_message keeps a legacy raw payload from degrading
    into a blank notification."""
    main.SFlowApp._on_transcription_error(stub, "No speech detected")

    assert stub.toasts[0].code == em.CODE_SILENCE


def test_silence_reads_differently_from_a_real_failure(stub):
    main.SFlowApp._on_transcription_error(stub, em.CODE_SILENCE)
    silence = stub.toasts[0]
    main.SFlowApp._on_transcription_error(stub, em.CODE_AUTH)
    auth = stub.toasts[1]

    assert silence.title != auth.title


def test_unknown_payload_still_produces_a_message(stub):
    main.SFlowApp._on_transcription_error(stub, "some unmapped failure")

    assert stub.toasts[0].code == em.CODE_UNKNOWN
    assert stub.toasts[0].body.strip()


# ---------- notify() itself ----------
class FakeTray:
    def __init__(self):
        self.messages = []

    def showMessage(self, title, body, icon, ms):
        self.messages.append((title, body))


class NotifyStub:
    def __init__(self, tray):
        self._tray = tray
        self._last_notify_code = ""
        self._last_notify_ts = 0.0


@pytest.fixture
def notifier(monkeypatch):
    monkeypatch.setattr(main.QSystemTrayIcon, "supportsMessages", staticmethod(lambda: True))
    return NotifyStub(FakeTray())


def test_notify_delivers_the_toast(notifier):
    main.SFlowApp.notify(notifier, em.message_for(em.CODE_OFFLINE))

    assert len(notifier._tray.messages) == 1
    assert notifier._tray.messages[0][0] == em.message_for(em.CODE_OFFLINE).title


def test_repeated_identical_errors_notify_once(notifier, monkeypatch):
    """Holding a broken hotkey bursts identical failures; one toast is enough."""
    monkeypatch.setattr(main.time, "time", lambda: 1000.0)

    for _ in range(5):
        main.SFlowApp.notify(notifier, em.message_for(em.CODE_OFFLINE))

    assert len(notifier._tray.messages) == 1


def test_a_different_error_breaks_through_the_throttle(notifier, monkeypatch):
    monkeypatch.setattr(main.time, "time", lambda: 1000.0)

    main.SFlowApp.notify(notifier, em.message_for(em.CODE_OFFLINE))
    main.SFlowApp.notify(notifier, em.message_for(em.CODE_AUTH))

    assert len(notifier._tray.messages) == 2


def test_notify_without_a_tray_is_a_no_op():
    """The tray is built after SFlowApp — an early error must not crash."""
    main.SFlowApp.notify(NotifyStub(None), em.message_for(em.CODE_OFFLINE))


def test_notify_survives_a_broken_tray(notifier, monkeypatch):
    """Notifications are additive; the pill is the real feedback. A failure to
    notify must never take down the dictation flow."""
    def boom(*_a):
        raise RuntimeError("notification center unavailable")
    monkeypatch.setattr(notifier._tray, "showMessage", boom)

    main.SFlowApp.notify(notifier, em.message_for(em.CODE_OFFLINE))
