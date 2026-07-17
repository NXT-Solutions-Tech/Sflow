"""API keys — macOS Keychain first, then a private .env parse. Never logs the key.

Reading precedence: Keychain (service "SFlow") → in-memory override → the app's
private .env parse → the OS environment. Writing goes to the Keychain.

The .env is parsed into a module-private dict here — deliberately NOT into
``os.environ``. A key in the environment leaks to every subprocess the app
spawns: numba/librosa (the local STT engines) launch "spawn" workers that
re-exec the binary, and each one would inherit ``GROQ_API_KEY`` for no reason.
Keeping the parse private means the key lives in exactly one process's heap.
"""
import os

try:
    import keyring
except Exception:  # keyring missing or backend unavailable
    keyring = None

SERVICE = "SFlow"

# Set at runtime when the app itself stores a key (e.g. the onboarding wizard),
# so the running process sees it immediately without a restart and without ever
# touching os.environ. Checked before the .env file.
_overrides: dict[str, str] = {}

# Parsed .env cache, keyed by the file path it was read from — tests repoint
# APP_DATA_DIR per-case, so keying on the path re-reads a different file instead
# of serving a stale parse.
_env_cache: dict[str, dict[str, str]] = {}


def _env_path() -> str:
    # Imported lazily (config loads everywhere first) and resolved at call time so
    # tests that repoint APP_DATA_DIR pick up their own .env.
    from config import APP_DATA_DIR
    return os.path.join(APP_DATA_DIR, ".env")


def _parse_env_file(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(path) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k:
                    values[k] = v
    except OSError:
        pass
    return values


def _dotenv(name: str) -> str:
    path = _env_path()
    if path not in _env_cache:
        _env_cache[path] = _parse_env_file(path)
    return _env_cache[path].get(name, "")


def set_runtime_key(name: str, value: str):
    """Make ``name`` visible to get_key for the rest of this process's life,
    without exporting it to the environment. Also drops the .env cache so a value
    just written to disk is re-read on the next lookup."""
    if value:
        _overrides[name] = value
    else:
        _overrides.pop(name, None)
    _env_cache.clear()


def get_key(name: str) -> str:
    """Return the key from Keychain, else runtime override, else .env, else env."""
    if keyring is not None:
        try:
            v = keyring.get_password(SERVICE, name)
            if v:
                return v
        except Exception:
            pass
    if _overrides.get(name):
        return _overrides[name]
    v = _dotenv(name)
    if v:
        return v
    return os.getenv(name, "")


def set_key(name: str, value: str) -> bool:
    """Store (or clear, if value is empty) the key in the Keychain. Returns success."""
    if keyring is None:
        return False
    try:
        if value:
            keyring.set_password(SERVICE, name, value)
        else:
            try:
                keyring.delete_password(SERVICE, name)
            except Exception:
                pass
        return True
    except Exception:
        return False


def key_source(name: str) -> str:
    """'keychain' | 'env' | 'none' — for UI status. Never returns the value."""
    if keyring is not None:
        try:
            if keyring.get_password(SERVICE, name):
                return "keychain"
        except Exception:
            pass
    if _overrides.get(name) or _dotenv(name) or os.getenv(name):
        return "env"
    return "none"
