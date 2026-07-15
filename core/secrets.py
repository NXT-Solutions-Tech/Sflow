"""API keys — macOS Keychain first, .env fallback. Never logs the key value.

Reading precedence: Keychain (service "SFlow") → environment (.env). Writing goes
to the Keychain. If `keyring` is unavailable (or the backend fails), we degrade
gracefully to the env var so the app never breaks over key storage.
"""
import os

try:
    import keyring
except Exception:  # keyring missing or backend unavailable
    keyring = None

SERVICE = "SFlow"


def get_key(name: str) -> str:
    """Return the key from Keychain, else from the environment, else ''."""
    if keyring is not None:
        try:
            v = keyring.get_password(SERVICE, name)
            if v:
                return v
        except Exception:
            pass
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
    return "env" if os.getenv(name) else "none"
