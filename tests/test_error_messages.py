"""Every failure must reach the user as words they can act on.

The Groq SDK classes are faked by NAME here, mirroring how error_messages
classifies them — that's what keeps the module free of a heavy SDK import.
"""
import pytest

from core import error_messages as em


# ---------- fake SDK exceptions (name-matched, like the real ones) ----------
class APIError(Exception):
    pass


class AuthenticationError(APIError):
    pass


class PermissionDeniedError(APIError):
    pass


class RateLimitError(APIError):
    pass


class APIConnectionError(APIError):
    pass


class APITimeoutError(APIConnectionError):
    """Mirrors the real SDK: a timeout IS a connection error subclass."""


class APIStatusError(APIError):
    pass


class InternalServerError(APIStatusError):
    pass


# ---------- classify_exception ----------
@pytest.mark.parametrize("exc,expected", [
    (AuthenticationError("401"), em.CODE_AUTH),
    (PermissionDeniedError("403"), em.CODE_AUTH),
    (RateLimitError("429"), em.CODE_RATE_LIMIT),
    (APIConnectionError("dns"), em.CODE_OFFLINE),
    (APITimeoutError("timed out"), em.CODE_TIMEOUT),
    (APIStatusError("500"), em.CODE_SERVER),
    (InternalServerError("500"), em.CODE_SERVER),
])
def test_classify_sdk_exceptions(exc, expected):
    assert em.classify_exception(exc) == expected


def test_timeout_wins_over_its_connection_error_parent():
    """APITimeoutError subclasses APIConnectionError — MRO order must resolve to
    the more specific 'timeout', not the generic 'offline'."""
    assert em.classify_exception(APITimeoutError("slow")) == em.CODE_TIMEOUT


def test_missing_key_valueerror_is_recognised():
    """The single most common real error, raised in three modules."""
    assert em.classify_exception(ValueError("GROQ_API_KEY not configured")) == em.CODE_NO_KEY


def test_unknown_exception_degrades_to_unknown():
    assert em.classify_exception(RuntimeError("something weird")) == em.CODE_UNKNOWN


def test_none_is_unknown_not_a_crash():
    assert em.classify_exception(None) == em.CODE_UNKNOWN


def test_a_subclass_of_a_known_sdk_error_still_resolves():
    class WeirdAuthError(AuthenticationError):
        pass
    assert em.classify_exception(WeirdAuthError("nope")) == em.CODE_AUTH


# ---------- classify_message ----------
@pytest.mark.parametrize("msg,expected", [
    ("No speech detected", em.CODE_SILENCE),
    ("No voice command detected", em.CODE_SILENCE),
    ("GROQ_API_KEY not configured", em.CODE_NO_KEY),
    ("", em.CODE_UNKNOWN),
    ("kaboom", em.CODE_UNKNOWN),
])
def test_classify_message(msg, expected):
    assert em.classify_message(msg) == expected


def test_classify_message_is_case_insensitive():
    assert em.classify_message("NO SPEECH DETECTED") == em.CODE_SILENCE


def test_passing_a_code_through_is_lossless():
    """main.py emits codes on the same signal that once carried raw strings."""
    for code in em.CODES:
        assert em.classify_message(code) == code


# ---------- message_for ----------
@pytest.mark.parametrize("code", em.CODES)
def test_every_code_has_actionable_copy(code):
    """A new code cannot ship without a message — that's the regression this
    whole module exists to prevent."""
    toast = em.message_for(code)
    assert toast.code == code
    assert toast.title.strip()
    assert toast.body.strip()
    assert len(toast.title) < 40  # notification titles get truncated


def test_unknown_code_degrades_instead_of_raising():
    assert em.message_for("not-a-real-code").code == em.CODE_UNKNOWN


def test_silence_and_real_failure_read_differently():
    """Distinguishing "you said nothing" from "we broke" is the point."""
    assert em.message_for(em.CODE_SILENCE).title != em.message_for(em.CODE_OFFLINE).title


def test_offline_message_points_at_the_local_engine():
    body = em.message_for(em.CODE_OFFLINE).body.lower()
    assert "local" in body


def test_paste_failure_reassures_the_text_is_not_lost():
    body = em.message_for(em.CODE_PASTE_FAILED).body.lower()
    assert "historial" in body


# ---------- should_notify ----------
def test_a_different_error_always_notifies():
    assert em.should_notify("offline", last_code="auth", last_ts=100.0, now=100.1) is True


def test_the_same_error_is_throttled():
    """Holding a broken hotkey bursts identical failures; one toast is enough."""
    assert em.should_notify("offline", last_code="offline", last_ts=100.0, now=101.0) is False


def test_the_same_error_notifies_again_after_the_window():
    assert em.should_notify("offline", last_code="offline", last_ts=100.0, now=106.0) is True


def test_the_first_error_ever_notifies():
    assert em.should_notify("offline", last_code="", last_ts=0.0, now=0.5) is True
