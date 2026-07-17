"""Shared test isolation: never touch the real settings.json / user data.

Data paths are resolved at *import* time (``LOG_PATH = os.path.join(APP_DATA_DIR,
...)`` at module level), so patching ``config.APP_DATA_DIR`` alone only covers
modules imported later — every already-loaded module keeps its own resolved copy
and would still append to the user's real sflow.log. Hence the sweep below:
rewrite the resolved symbols in each loaded module, *and* patch the config
constant so any later import derives from tmp_path too.
"""
import sys
import pytest
import config

# Our own modules only — patching a stdlib/3rd-party module that happens to
# expose a same-named attribute would be a bug, not isolation.
_OWN_NAMES = {"config", "main"}
_OWN_PREFIXES = ("core.", "ui.", "db.", "web.")

# Resolved-at-import log paths → basename to re-point inside tmp_path.
# core.hotkey keeps a second, independent logger; both leak without this.
_LOG_ATTRS = {
    "LOG_PATH": "sflow.log",     # core.logger
    "_LOG_PATH": "hotkey.log",   # core.hotkey
}


def _own_modules():
    for name, mod in list(sys.modules.items()):
        if mod is None:
            continue
        if name in _OWN_NAMES or name.startswith(_OWN_PREFIXES):
            yield mod


@pytest.fixture(autouse=True)
def _isolate_settings(tmp_path, monkeypatch):
    data_dir = tmp_path / "appdata"
    data_dir.mkdir()

    monkeypatch.setattr(config, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(config, "APP_DATA_DIR", str(data_dir))

    for mod in _own_modules():
        if hasattr(mod, "APP_DATA_DIR"):
            monkeypatch.setattr(mod, "APP_DATA_DIR", str(data_dir))
        for attr, filename in _LOG_ATTRS.items():
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, str(data_dir / filename))

    config._SETTINGS = config._default_settings()

    # Secrets keeps process-global state (runtime overrides + a per-path .env
    # cache). Without clearing it a key stored in one test would bleed into the
    # next, and a cached .env parse for a since-deleted tmp path would be stale.
    try:
        import core.secrets as _secrets
        _secrets._overrides.clear()
        _secrets._env_cache.clear()
    except Exception:
        pass

    yield
