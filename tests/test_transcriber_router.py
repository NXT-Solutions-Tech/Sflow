"""Transcriber router: local→Groq fallback (the headline reliability feature)
and post-processing pipeline order. Uses a fake backend — no MLX, no network."""
import io

from core.transcriber import Transcriber


class FakeBackend:
    def __init__(self, available=True, text="hola", model_id="fake"):
        self.available = available
        self._text = text
        self.model_id = model_id
        self.calls = 0

    def transcribe(self, buf, vocabulary_prompt=""):
        self.calls += 1
        return self._text


def _model(engine="whisper", model="m", _id="x"):
    return {"engine": engine, "model": model, "id": _id, "local": engine != "groq"}


def test_resolve_falls_back_to_groq_when_local_unavailable(monkeypatch):
    t = Transcriber()
    monkeypatch.setattr("core.transcriber.get_stt_model", lambda: _model())
    t._backends["whisper|m"] = FakeBackend(available=False)
    _, engine = t._resolve()
    assert engine == "groq"


def test_resolve_uses_local_when_available(monkeypatch):
    t = Transcriber()
    monkeypatch.setattr("core.transcriber.get_stt_model", lambda: _model())
    t._backends["whisper|m"] = FakeBackend(available=True)
    _, engine = t._resolve()
    assert engine == "whisper"


def test_runtime_failure_falls_back_to_groq(monkeypatch):
    """A local engine that raises at transcribe-time (e.g. model download drop)
    must fall back to Groq, not surface an error."""
    t = Transcriber()
    monkeypatch.setattr("core.transcriber.get_stt_model", lambda: _model())

    class Boom(FakeBackend):
        def transcribe(self, buf, vocabulary_prompt=""):
            raise RuntimeError("HF download failed")

    t._backends["whisper|m"] = Boom(available=True)
    monkeypatch.setattr(t._groq, "transcribe", lambda buf, vocabulary_prompt="": "desde groq")
    monkeypatch.setattr("core.transcriber.get_setting",
                        lambda k, d=None: "none" if k == "auto_cleanup_level" else False)
    out, _ = t.transcribe(io.BytesIO(b"x"))
    assert out == "desde groq"


def test_pipeline_applies_smart_commands(monkeypatch):
    t = Transcriber()
    monkeypatch.setattr("core.transcriber.get_stt_model", lambda: _model())
    t._backends["whisper|m"] = FakeBackend(available=True, text="uno coma dos", model_id="x")
    flags = {"smart_commands_enabled": True, "auto_cleanup_level": "none"}
    monkeypatch.setattr("core.transcriber.get_setting", lambda k, d=None: flags.get(k, False))
    out, mid = t.transcribe(io.BytesIO(b"x"))
    assert out == "uno, dos"
    assert mid == "x"


def test_empty_transcript_short_circuits(monkeypatch):
    t = Transcriber()
    monkeypatch.setattr("core.transcriber.get_stt_model", lambda: _model())
    t._backends["whisper|m"] = FakeBackend(available=True, text="", model_id="x")
    monkeypatch.setattr("core.transcriber.get_setting", lambda k, d=None: False)
    out, mid = t.transcribe(io.BytesIO(b"x"))
    assert out == "" and mid == "x"
