"""The API key must never live in os.environ — subprocesses inherit it.

numba/librosa (the local STT engines) launch "spawn" workers that re-exec the
binary; a key in the environment would be handed to each one for no reason. The
.env is parsed into a process-private dict in core/secrets instead.
"""
import os
import subprocess
import sys

import config
import core.secrets as S
from core import onboarding


def test_dotenv_is_read_without_touching_environ(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(S, "keyring", None)
    S._env_cache.clear()
    S._overrides.clear()
    monkeypatch.delenv("MYKEY", raising=False)
    (tmp_path / ".env").write_text('MYKEY="gsk_secret"\n')

    assert S.get_key("MYKEY") == "gsk_secret"
    assert S.key_source("MYKEY") == "env"
    assert "MYKEY" not in os.environ  # parsed privately, never exported


def test_runtime_override_is_visible_without_env(monkeypatch):
    monkeypatch.setattr(S, "keyring", None)
    monkeypatch.delenv("KX", raising=False)
    S.set_runtime_key("KX", "v")

    assert S.get_key("KX") == "v"
    assert "KX" not in os.environ


def test_store_api_key_does_not_export_to_environ(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "keyring", None)  # force the .env fallback
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    key = "gsk_" + "a" * 40

    onboarding.store_api_key(key, str(tmp_path))

    assert "GROQ_API_KEY" not in os.environ
    assert S.get_key("GROQ_API_KEY") == key  # but the running process sees it


def test_a_stored_key_does_not_leak_into_a_subprocess(tmp_path, monkeypatch):
    """End-to-end: a spawned child (how numba workers re-exec) sees nothing."""
    monkeypatch.setattr(S, "keyring", None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    onboarding.store_api_key("gsk_" + "c" * 40, str(tmp_path))

    out = subprocess.run(
        [sys.executable, "-c", "import os; print(os.environ.get('GROQ_API_KEY', ''))"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""
