"""Shared test isolation: never touch the real settings.json / user data."""
import pytest
import config


@pytest.fixture(autouse=True)
def _isolate_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    config._SETTINGS = config._default_settings()
    yield
