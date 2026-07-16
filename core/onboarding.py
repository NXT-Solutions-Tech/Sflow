"""Onboarding & error-resolution logic — the *pure* brain behind the guided
first-run wizard and the informative error surface.

Everything here is import-safe on any OS: macOS-only APIs (Accessibility,
Input Monitoring) are imported lazily inside the functions that need them, so
this module can be unit-tested headless (no PyQt6 / AppKit required).

Three concerns live here:

1. **Key-optional resolution** — whether the app needs a cloud API key at all.
   Local STT models run 100% offline; a key is only required when the active
   model is a cloud model or Auto Cleanup (cloud LLM) is enabled.
2. **Error → message mapping** — turn a raw exception/string into a short,
   actionable Spanish message, distinguishing *silence* from a *real failure*.
3. **Permission probes** — thin wrappers over the macOS permission checks the
   wizard polls (safe no-ops off macOS).
"""
from __future__ import annotations

from config import get_stt_model, get_setting


# ---------------------------------------------------------------------------
# 1. Key-optional resolution
# ---------------------------------------------------------------------------
def api_key_required() -> bool:
    """True when the current settings genuinely need a cloud API key.

    Offline (local) STT needs no key. A key becomes necessary only if the
    active STT model is a cloud model, or Auto Cleanup is on (the LLM cleanup
    pass runs in the cloud). Everything else runs fully offline.
    """
    model = get_stt_model()
    if not model.get("local", False):
        return True
    if get_setting("auto_cleanup_level", "none") != "none":
        return True
    return False


def api_key_step_mode() -> str:
    """How the wizard should present the API-key step: 'required' | 'optional'.

    Never 'skip' — a local-only user may still want to add a key to unlock
    cloud fallback later, so the step is always shown, just optional.
    """
    return "required" if api_key_required() else "optional"


def has_api_key() -> bool:
    """True if a Groq key is already available (Keychain or environment)."""
    try:
        from core.secrets import get_key
        if get_key("GROQ_API_KEY"):
            return True
    except Exception:
        pass
    import os
    return bool(os.getenv("GROQ_API_KEY"))


def is_groq_key_valid(key: str) -> bool:
    """Shape check for a Groq key (prefix + length). Empty is *not* valid."""
    key = (key or "").strip()
    return key.startswith("gsk_") and len(key) >= 20


# ---------------------------------------------------------------------------
# 2. Error → actionable message
# ---------------------------------------------------------------------------
# kind → short, actionable Spanish text shown in the pill tooltip/notification.
ERROR_MESSAGES: dict[str, str] = {
    "silence": "No se detectó voz",
    "network": "Sin conexión",
    "auth": "API key inválida",
    "accessibility": "Falta permiso de Accesibilidad",
    "unknown": "Error de transcripción",
}

# Substrings (matched case-insensitively) that identify each failure class.
# Order matters: the first kind whose markers match wins, so the list below is
# ordered most-specific → least-specific.
_ERROR_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("silence", ("no speech", "no voice", "no se detect", "empty transcription")),
    ("auth", (
        "invalid api key", "invalid_api_key", "api key", "api_key",
        "authentication", "unauthorized", "401", "403", "permission denied on key",
    )),
    ("network", (
        "connection", "network", "timed out", "timeout", "getaddrinfo",
        "max retries", "temporarily unavailable", "name resolution",
        "unreachable", "sin conexión", "failed to establish", "connect",
        "read timed out", "ssl", "proxy",
    )),
    ("accessibility", (
        "accessibility", "not trusted", "axisprocesstrusted", "axtrusted",
        "accesibilidad", "not authorized to send", "not permitted",
        "cgevent", "keystroke",
    )),
]


def classify_error(err: object) -> str:
    """Map an exception (or message string) to an error *kind*.

    Returns one of: 'silence' | 'network' | 'auth' | 'accessibility' | 'unknown'.
    'silence' is deliberately distinct so the caller can treat "you said
    nothing" gently instead of flashing a real-failure indicator.
    """
    msg = str(err if err is not None else "").strip().lower()
    if not msg:
        return "unknown"
    for kind, markers in _ERROR_MARKERS:
        if any(m in msg for m in markers):
            return kind
    return "unknown"


def error_message(err: object) -> str:
    """Human, actionable Spanish message for a raw error."""
    return ERROR_MESSAGES[classify_error(err)]


def is_silence(err: object) -> bool:
    """True when the 'error' is just the user not speaking (not a failure)."""
    return classify_error(err) == "silence"


# ---------------------------------------------------------------------------
# 3. Permission probes (macOS; safe no-ops elsewhere)
# ---------------------------------------------------------------------------
def accessibility_trusted(prompt: bool = False) -> bool:
    """Is SFlow trusted for Accessibility (keystroke paste)?

    `prompt=True` asks macOS to add SFlow to the Accessibility list and show
    the system prompt. Off macOS (or if ApplicationServices is unavailable)
    this returns True so headless/dev flows never block.
    """
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions
        return bool(AXIsProcessTrustedWithOptions(
            {"AXTrustedCheckOptionPrompt": bool(prompt)}
        ))
    except Exception:
        return True


# URL schemes that deep-link straight to the relevant System Settings pane.
ACCESSIBILITY_PANE = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)
INPUT_MONITORING_PANE = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
)
MICROPHONE_PANE = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
)


def open_settings_pane(url: str) -> bool:
    """Open a System Settings privacy pane by URL scheme. Best-effort."""
    try:
        import subprocess
        subprocess.Popen(["open", url])
        return True
    except Exception:
        return False
