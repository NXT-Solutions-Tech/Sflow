"""Router is local-first: a selected local model whose weights are missing falls
back to the bundled Parakeet before ever touching the cloud, and a runtime
ModelNotDownloaded surfaces honestly instead of becoming a false Groq/no-key error."""
import io

import pytest

from core.transcriber import Transcriber, _PARAKEET_REPO
from core.models import ModelNotDownloaded


class FakeBackend:
    def __init__(self, available=True, downloaded=True, text="hola", model_id="fake", raises=None):
        self.available = available
        self._downloaded = downloaded
        self._text = text
        self.model_id = model_id
        self._raises = raises

    def is_downloaded(self):
        return self._downloaded

    def transcribe(self, buf, vocabulary_prompt=""):
        if self._raises:
            raise self._raises
        return self._text


def _model(engine="whisper", model="m", _id="x"):
    return {"engine": engine, "model": model, "id": _id, "local": engine != "groq"}


def test_selected_local_not_downloaded_falls_back_to_bundled_parakeet(monkeypatch):
    t = Transcriber()
    monkeypatch.setattr("core.transcriber.get_stt_model", lambda: _model())
    t._backends["whisper|m"] = FakeBackend(available=True, downloaded=False)
    t._backends[f"parakeet|{_PARAKEET_REPO}"] = FakeBackend(available=True, downloaded=True, model_id="pk")

    _, engine = t._resolve()

    assert engine == "parakeet"  # still on-device, never the cloud


def test_no_local_available_falls_back_to_groq(monkeypatch):
    t = Transcriber()
    monkeypatch.setattr("core.transcriber.get_stt_model", lambda: _model())
    t._backends["whisper|m"] = FakeBackend(available=True, downloaded=False)
    # bundled parakeet also missing
    t._backends[f"parakeet|{_PARAKEET_REPO}"] = FakeBackend(available=True, downloaded=False)

    _, engine = t._resolve()

    assert engine == "groq"


def test_downloaded_local_model_is_used_directly(monkeypatch):
    t = Transcriber()
    monkeypatch.setattr("core.transcriber.get_stt_model", lambda: _model())
    t._backends["whisper|m"] = FakeBackend(available=True, downloaded=True)

    _, engine = t._resolve()

    assert engine == "whisper"


def test_runtime_model_not_downloaded_is_not_swallowed_into_groq(monkeypatch):
    """The false-error path this replaces: a missing model must surface as
    ModelNotDownloaded (→ CODE_MODEL_MISSING), never a silent Groq attempt."""
    t = Transcriber()
    monkeypatch.setattr("core.transcriber.get_stt_model", lambda: _model())
    t._backends["whisper|m"] = FakeBackend(available=True, downloaded=True,
                                           raises=ModelNotDownloaded("repo"))
    monkeypatch.setattr("core.transcriber.get_setting", lambda k, d=None: False)
    # Groq would answer if we fell back — assert we do NOT.
    monkeypatch.setattr(t._groq, "transcribe", lambda buf, vocabulary_prompt="": "desde groq")

    with pytest.raises(ModelNotDownloaded):
        t.transcribe(io.BytesIO(b"x"))
