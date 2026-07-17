"""Orphan settings are gone from the defaults, but legacy migration off an
existing file still works (it reads the loaded file, not the defaults)."""
import json

import config


def test_orphan_settings_are_gone_from_defaults():
    d = config._default_settings()
    for dead in ("llm_model", "history_hotkey_enabled",
                 "transcribe_backend", "llm_cleanup_enabled"):
        assert dead not in d, f"{dead} should have been removed from defaults"


def test_real_settings_survive():
    d = config._default_settings()
    assert "sound_on_start" in d and "sound_on_done" in d
    assert d["stt_model"] == "whisper-turbo-local"


def test_legacy_migration_still_works_off_a_file(tmp_path, monkeypatch):
    """Removing the legacy keys from DEFAULTS must not break migrating a file
    that still carries them."""
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"transcribe_backend": "groq", "llm_cleanup_enabled": True}))
    monkeypatch.setattr(config, "SETTINGS_PATH", str(p))

    s = config.load_settings()

    assert s["stt_model"] == "groq-turbo"
    assert s["auto_cleanup_level"] == "light"
