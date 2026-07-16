"""Pure onboarding / error-resolution logic (headless — no PyQt6 / AppKit).

Covers the three brains the guided wizard and the informative-error surface
rely on: key-optional resolution, error→message mapping, and key shape checks.
"""
import config
import core.onboarding as ob


# ---------------------------------------------------------------------------
# Key-optional resolution
# ---------------------------------------------------------------------------
def test_api_key_optional_for_local_model_without_cleanup():
    config.set_setting("stt_model", "whisper-turbo-local")
    config.set_setting("auto_cleanup_level", "none")
    assert ob.api_key_required() is False
    assert ob.api_key_step_mode() == "optional"


def test_api_key_required_for_cloud_model():
    config.set_setting("stt_model", "groq-turbo")
    config.set_setting("auto_cleanup_level", "none")
    assert ob.api_key_required() is True
    assert ob.api_key_step_mode() == "required"


def test_api_key_required_when_cleanup_enabled_even_if_local():
    config.set_setting("stt_model", "whisper-turbo-local")
    config.set_setting("auto_cleanup_level", "medium")
    assert ob.api_key_required() is True
    assert ob.api_key_step_mode() == "required"


def test_parakeet_local_is_offline():
    config.set_setting("stt_model", "parakeet-v3")
    config.set_setting("auto_cleanup_level", "none")
    assert ob.api_key_required() is False


# ---------------------------------------------------------------------------
# Groq key shape
# ---------------------------------------------------------------------------
def test_is_groq_key_valid():
    assert ob.is_groq_key_valid("gsk_" + "x" * 20) is True
    assert ob.is_groq_key_valid("sk-wrongprefix" + "x" * 20) is False
    assert ob.is_groq_key_valid("gsk_short") is False
    assert ob.is_groq_key_valid("") is False
    assert ob.is_groq_key_valid(None) is False
    assert ob.is_groq_key_valid("  gsk_" + "y" * 20 + "  ") is True  # trimmed


# ---------------------------------------------------------------------------
# Error → kind / message
# ---------------------------------------------------------------------------
def test_silence_is_distinguished_from_failure():
    assert ob.classify_error("No speech detected") == "silence"
    assert ob.classify_error("No voice command detected") == "silence"
    assert ob.classify_error("No se detectó voz") == "silence"
    assert ob.is_silence("No speech detected") is True
    assert ob.is_silence("Connection error") is False


def test_network_errors():
    for m in [
        "Connection error.",
        "Max retries exceeded with url",
        "Read timed out",
        "Failed to establish a new connection: getaddrinfo failed",
        "Service temporarily unavailable",
    ]:
        assert ob.classify_error(m) == "network", m
    assert ob.error_message("Connection error.") == "Sin conexión"


def test_auth_errors():
    for m in [
        "Invalid API Key",
        "invalid_api_key",
        "Error code: 401 - Unauthorized",
        "authentication failed",
    ]:
        assert ob.classify_error(m) == "auth", m
    assert ob.error_message("Invalid API Key") == "API key inválida"


def test_accessibility_errors():
    for m in [
        "Accessibility permission denied",
        "AXIsProcessTrusted returned false",
        "not authorized to send Apple events",
        "CGEvent unavailable",
    ]:
        assert ob.classify_error(m) == "accessibility", m
    assert ob.error_message("Accessibility denied") == "Falta permiso de Accesibilidad"


def test_unknown_and_empty():
    assert ob.classify_error("") == "unknown"
    assert ob.classify_error(None) == "unknown"
    assert ob.classify_error("something totally weird happened") == "unknown"
    assert ob.error_message("boom") == "Error de transcripción"


def test_classify_accepts_exception_objects():
    assert ob.classify_error(RuntimeError("Connection error")) == "network"
    assert ob.classify_error(ValueError("No speech detected")) == "silence"


def test_marker_ordering_silence_wins_over_generic():
    # A message that mentions "connect" but is really about no speech should
    # not be miscategorised — silence markers are checked first.
    assert ob.classify_error("No speech detected while connecting mic") == "silence"


# ---------------------------------------------------------------------------
# Permission probe is a safe no-op off macOS
# ---------------------------------------------------------------------------
def test_accessibility_trusted_safe_offmac():
    # ApplicationServices is unavailable in CI/Linux → returns True (never blocks).
    assert ob.accessibility_trusted() is True
