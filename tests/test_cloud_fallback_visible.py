"""The cloud fallback must never be silent.

When the user picks a LOCAL engine and the router transcribes via Groq anyway,
the audio left the device. `_was_cloud_fallback` is what turns that into an
amber pill instead of a plain success check, so it gets its own guard.
"""
import config
from main import _was_cloud_fallback


def _use(model_id: str, monkeypatch):
    monkeypatch.setattr(config, "_SETTINGS", dict(config._SETTINGS, stt_model=model_id))


def test_local_engine_transcribing_locally_is_not_a_fallback(monkeypatch):
    _use("whisper-turbo-local", monkeypatch)
    assert _was_cloud_fallback("mlx-community/whisper-large-v3-turbo") is False


def test_local_engine_transcribing_in_cloud_is_a_fallback(monkeypatch):
    """The headline case: label says "offline", audio went to Groq."""
    _use("whisper-turbo-local", monkeypatch)
    assert _was_cloud_fallback("whisper-large-v3-turbo") is True


def test_parakeet_falling_back_is_a_fallback(monkeypatch):
    _use("parakeet-v3", monkeypatch)
    assert _was_cloud_fallback("whisper-large-v3-turbo") is True


def test_cloud_model_is_never_a_fallback(monkeypatch):
    """The user chose the cloud — no surprise to surface."""
    _use("groq-turbo", monkeypatch)
    assert _was_cloud_fallback("whisper-large-v3-turbo") is False
