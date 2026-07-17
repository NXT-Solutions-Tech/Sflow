"""Groq STT timeout scales with the WAV upload — a flat 10s dropped long
dictations on a slow uplink."""
import io

import pytest

from core.transcriber_groq import GroqTranscriber, _stt_timeout


def test_small_clip_gets_the_base_timeout():
    assert _stt_timeout(0) == 10.0
    assert _stt_timeout(50_000) == pytest.approx(10.5)


def test_a_long_dictation_gets_more_time():
    # ~5-minute WAV ≈ 9.6MB → far more than the flat 10s that used to drop it.
    assert _stt_timeout(9_600_000) > 10.0


def test_capped_so_a_huge_file_cannot_hang_forever():
    assert _stt_timeout(100_000_000) == 60.0


class _FakeCreate:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return "hola"


class _FakeClient:
    def __init__(self, create):
        self.audio = type("A", (), {"transcriptions": create})()


def test_transcribe_passes_the_scaled_timeout(monkeypatch):
    tr = GroqTranscriber()
    fake = _FakeCreate()
    monkeypatch.setattr(tr, "_get_client", lambda: _FakeClient(fake))
    data = b"x" * 500_000
    tr.transcribe(io.BytesIO(data))
    assert fake.kwargs["timeout"] == pytest.approx(_stt_timeout(len(data)))
