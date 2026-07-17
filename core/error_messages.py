"""Failures → something the user can act on.

Every dictation failure used to collapse into the same 1.2s red X: the error
string reached the handler and was thrown away. "Sin conexión" and "API key
inválida" need different reactions from the user, so they need different words.

Classification matches exception *class names* across the MRO rather than
importing the Groq SDK, which keeps this module free of heavy imports and
testable with hand-rolled fakes.
"""
from __future__ import annotations

from typing import NamedTuple

# Silence is not a failure — it's the most common outcome of a mis-tapped hotkey
# and deserves its own calm message rather than an alarming error.
CODE_SILENCE = "silence"
CODE_HALLUCINATION = "hallucination"
CODE_NO_KEY = "no_key"
CODE_AUTH = "auth"
CODE_RATE_LIMIT = "rate_limit"
CODE_OFFLINE = "offline"
CODE_TIMEOUT = "timeout"
CODE_SERVER = "server"
CODE_PERMISSION = "permission"
CODE_PASTE_FAILED = "paste_failed"
CODE_NO_SELECTION = "no_selection"
CODE_UNKNOWN = "unknown"

CODES = (
    CODE_SILENCE, CODE_HALLUCINATION, CODE_NO_KEY, CODE_AUTH, CODE_RATE_LIMIT,
    CODE_OFFLINE, CODE_TIMEOUT, CODE_SERVER, CODE_PERMISSION, CODE_PASTE_FAILED,
    CODE_NO_SELECTION, CODE_UNKNOWN,
)


class Toast(NamedTuple):
    code: str
    title: str
    body: str


_MESSAGES = {
    CODE_SILENCE: Toast(
        CODE_SILENCE, "No se detectó voz",
        "Mantén el atajo presionado mientras hablas.",
    ),
    CODE_HALLUCINATION: Toast(
        CODE_HALLUCINATION, "No se detectó voz",
        "Solo se oyó ruido de fondo. Acércate al micrófono e intenta de nuevo.",
    ),
    CODE_NO_KEY: Toast(
        CODE_NO_KEY, "Falta la API key",
        "Este modelo usa la nube. Añade tu key en Ajustes o cambia a Whisper Turbo local.",
    ),
    CODE_AUTH: Toast(
        CODE_AUTH, "API key inválida",
        "Groq rechazó tu key. Revísala en el Hub → Ajustes.",
    ),
    CODE_RATE_LIMIT: Toast(
        CODE_RATE_LIMIT, "Límite de Groq alcanzado",
        "Espera un momento o cambia a Whisper Turbo local en Ajustes.",
    ),
    CODE_OFFLINE: Toast(
        CODE_OFFLINE, "Sin conexión",
        "Groq necesita internet. Cambia a Whisper Turbo local en Ajustes para dictar offline.",
    ),
    CODE_TIMEOUT: Toast(
        CODE_TIMEOUT, "Groq tardó demasiado",
        "La red va lenta. Reintenta o cambia a Whisper Turbo local en Ajustes.",
    ),
    CODE_SERVER: Toast(
        CODE_SERVER, "Groq no responde",
        "El servicio falló. Reintenta en un momento o usa Whisper Turbo local.",
    ),
    CODE_PERMISSION: Toast(
        CODE_PERMISSION, "Falta permiso de Accesibilidad",
        "SFlow no puede escribir en otras apps. Concédelo en Ajustes del sistema.",
    ),
    CODE_PASTE_FAILED: Toast(
        CODE_PASTE_FAILED, "No se pudo pegar",
        "Falta el permiso de Accesibilidad. Tu texto está guardado en el historial.",
    ),
    CODE_NO_SELECTION: Toast(
        CODE_NO_SELECTION, "No hay texto seleccionado",
        "Selecciona el texto que quieres transformar y vuelve a intentarlo.",
    ),
    CODE_UNKNOWN: Toast(
        CODE_UNKNOWN, "Algo falló",
        "No se pudo completar el dictado. Revisa sflow.log si se repite.",
    ),
}

# Groq SDK class names → code. Matched by name so the SDK stays unimported.
_EXCEPTION_NAMES = {
    "AuthenticationError": CODE_AUTH,
    "PermissionDeniedError": CODE_AUTH,
    "RateLimitError": CODE_RATE_LIMIT,
    "APIConnectionError": CODE_OFFLINE,
    "APITimeoutError": CODE_TIMEOUT,
    "InternalServerError": CODE_SERVER,
    "APIStatusError": CODE_SERVER,
}


def classify_message(msg: str) -> str:
    """Map a raw error/status string to a code."""
    text = (msg or "").strip().lower()
    if not text:
        return CODE_UNKNOWN
    if text in CODES:
        return text  # already a code — passing one through must be lossless
    if "no speech detected" in text or "no voice command detected" in text:
        return CODE_SILENCE
    if "not configured" in text and "key" in text:
        return CODE_NO_KEY
    if "accessibility" in text or "not trusted" in text:
        return CODE_PERMISSION
    return CODE_UNKNOWN


def classify_exception(exc: BaseException) -> str:
    """Map an exception to a code, walking the MRO so SDK subclasses resolve to
    their closest known ancestor (APITimeoutError before APIConnectionError,
    which is why order follows the MRO rather than the dict)."""
    if exc is None:
        return CODE_UNKNOWN
    for klass in type(exc).__mro__:
        code = _EXCEPTION_NAMES.get(klass.__name__)
        if code:
            return code
    return classify_message(str(exc))


def message_for(code: str) -> Toast:
    """The user-facing toast for a code. Unknown codes degrade to the generic
    message rather than raising — a bad code must never break error reporting."""
    return _MESSAGES.get(code, _MESSAGES[CODE_UNKNOWN])


def should_notify(code: str, last_code: str, last_ts: float,
                  now: float, window: float = 5.0) -> bool:
    """Throttle repeats: the same failure within ``window`` seconds stays quiet.

    Holding a hotkey that can't work produces a burst of identical failures, and
    a stack of identical notifications is worse than one.
    """
    if code != last_code:
        return True
    return (now - (last_ts or 0)) >= window
