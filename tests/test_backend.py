"""Backend logic: substitutions, dictionary, smart commands, STT language, config migration."""
import json
import config
import core.dictionary as d
import core.substitutions as subs
import core.smart_commands as sc


def _write_dict(monkeypatch, tmp_path, content):
    p = tmp_path / "dict.txt"
    p.write_text(content)
    monkeypatch.setattr(d, "DICTIONARY_PATH", str(p))
    return p


def test_substitutions_parse_all_arrows(monkeypatch, tmp_path):
    _write_dict(monkeypatch, tmp_path, "Daniel\nbtw -> by the way\ntbh => to be honest\nq → que\n")
    s = dict(d.load_substitutions())
    assert s["btw"] == "by the way"
    assert s["tbh"] == "to be honest"
    assert s["q"] == "que"


def test_substitutions_apply_word_boundary_and_case(monkeypatch, tmp_path):
    _write_dict(monkeypatch, tmp_path, "btw -> by the way\n")
    assert subs.apply("btw I like it") == "by the way I like it"
    assert subs.apply("Btw listo") == "By the way listo"       # capital preserved
    assert subs.apply("subtbw btws") == "subtbw btws"          # no partial match


def test_whisper_prompt_excludes_substitutions(monkeypatch, tmp_path):
    _write_dict(monkeypatch, tmp_path, "Daniel Carreón\nbtw -> by the way\n")
    hint = d.as_whisper_prompt()
    assert "Daniel Carreón" in hint
    assert "->" not in hint and "by the way" not in hint


def test_smart_commands_newline():
    assert "\n" in sc.apply("uno nueva linea dos")


def test_stt_language_resolver():
    config.set_setting("stt_language", "auto")
    assert config.get_stt_language() is None
    config.set_setting("stt_language", "es")
    assert config.get_stt_language() == "es"


def test_migration_cleanup_enabled_to_level(monkeypatch, tmp_path):
    p = tmp_path / "s.json"
    monkeypatch.setattr(config, "SETTINGS_PATH", str(p))
    p.write_text(json.dumps({"llm_cleanup_enabled": True}))
    assert config.load_settings()["auto_cleanup_level"] == "light"
    p.write_text(json.dumps({"llm_cleanup_enabled": False}))
    assert config.load_settings()["auto_cleanup_level"] == "none"


def test_migration_transcribe_backend_to_stt_model(monkeypatch, tmp_path):
    p = tmp_path / "s.json"
    monkeypatch.setattr(config, "SETTINGS_PATH", str(p))
    p.write_text(json.dumps({"transcribe_backend": "groq"}))
    assert config.load_settings()["stt_model"] == "groq-turbo"
