"""Tiny i18n — ``tr(key, **fmt)`` resolves against the active language.

Language = setting ``language`` ('auto' | 'es' | 'en'). 'auto' follows the system
locale (QLocale). The catalog is ``{key: {'es': ..., 'en': ...}}``; a completeness
test enforces that EVERY key has both languages and there are no orphans, so a
half-translated string can never ship.

Spanish is the source language: an unknown key returns itself (visible in dev,
never a crash), and a missing translation falls back to Spanish.
"""
from config import get_setting

_DEFAULT_LANG = "es"
LANGUAGES = ("es", "en")


# key → {es, en}. Grouped by surface. Titles kept < 40 chars (notification limit).
CATALOG: dict[str, dict[str, str]] = {
    # ---- tray ----
    "tray.status": {"es": "SFlow — Activo", "en": "SFlow — Active"},
    "tray.open_hub": {"es": "Abrir Hub  (⌘⇧H)", "en": "Open Hub  (⌘⇧H)"},
    "tray.launch_login": {"es": "Iniciar con macOS", "en": "Launch at login"},
    "tray.relaunch": {"es": "Reiniciar SFlow", "en": "Restart SFlow"},
    "tray.quit": {"es": "Salir", "en": "Quit"},
    "tray.tooltip": {"es": "SFlow — Voz a Texto", "en": "SFlow — Voice to Text"},

    # ---- sidebar nav ----
    "nav.home": {"es": "Inicio", "en": "Home"},
    "nav.insights": {"es": "Métricas", "en": "Insights"},
    "nav.history": {"es": "Historial", "en": "History"},
    "nav.dictionary": {"es": "Diccionario", "en": "Dictionary"},
    "nav.snippets": {"es": "Snippets", "en": "Snippets"},
    "nav.settings": {"es": "Ajustes", "en": "Settings"},

    # ---- page titles ----
    "page.history": {"es": "Historial", "en": "History"},
    "page.dictionary": {"es": "Diccionario personal", "en": "Personal dictionary"},
    "page.snippets": {"es": "Snippets", "en": "Snippets"},
    "page.settings": {"es": "Ajustes", "en": "Settings"},
    "page.insights": {"es": "Métricas", "en": "Insights"},

    # ---- settings: general ----
    "settings.language": {"es": "Idioma de la app", "en": "App language"},
    "settings.lang_auto": {"es": "Automático (según el sistema)", "en": "Automatic (follow system)"},
    "settings.lang_es": {"es": "Español", "en": "Spanish"},
    "settings.lang_en": {"es": "Inglés", "en": "English"},
    "settings.save": {"es": "Guardar ajustes", "en": "Save settings"},
    "settings.saved_title": {"es": "Guardado", "en": "Saved"},
    "settings.saved_body": {"es": "Ajustes guardados.", "en": "Settings saved."},
    "settings.lang_hint": {"es": "Se aplica al reabrir el Hub.", "en": "Applies when you reopen the Hub."},

    # ---- wizard: model step ----
    "wizard.model_title": {"es": "Mejor precisión (opcional)", "en": "Better accuracy (optional)"},
    "wizard.model_body": {
        "es": "Parakeet ya viene incluido y funciona offline. Whisper Turbo acierta más "
              "en nombres y jerga; es una descarga única de ~1.6 GB que puedes hacer ahora "
              "o después desde Ajustes → Modelo.",
        "en": "Parakeet is already bundled and works offline. Whisper Turbo is more accurate "
              "on names and jargon; it's a one-time ~1.6 GB download you can do now or later "
              "from Settings → Model.",
    },
    "wizard.model_download": {"es": "Descargar Whisper Turbo (1.6 GB)", "en": "Download Whisper Turbo (1.6 GB)"},
    "wizard.model_later": {"es": "Después", "en": "Later"},
    "wizard.model_have_it": {"es": "Ya descargado ✓", "en": "Already downloaded ✓"},

    # ---- model download dialog ----
    "download.title": {"es": "Descargar modelo", "en": "Download model"},
    "download.subtitle": {"es": "Descarga única · ~{size} MB · se guarda en tu Mac para uso offline.",
                          "en": "One-time download · ~{size} MB · stored on your Mac for offline use."},
    "download.cancel": {"es": "Cancelar", "en": "Cancel"},
    "download.done_btn": {"es": "Listo", "en": "Done"},
    "download.preparing": {"es": "Preparando…", "en": "Preparing…"},
    "download.progress": {"es": "Descargando… {pct}%", "en": "Downloading… {pct}%"},
    "download.complete": {"es": "Descarga completa ✓", "en": "Download complete ✓"},
    "download.failed": {"es": "No se pudo descargar. Revisa tu conexión e intenta de nuevo.",
                        "en": "Download failed. Check your connection and try again."},
    "download.cancelling": {"es": "Cancelando…", "en": "Cancelling…"},

    # ---- settings: model picker download affordance ----
    "settings.model_missing": {"es": "No descargado — necesario para dictar offline con este modelo.",
                               "en": "Not downloaded — required to dictate offline with this model."},
    "settings.model_ready": {"es": "Descargado ✓ · listo para dictar offline.",
                             "en": "Downloaded ✓ · ready to dictate offline."},
    "settings.download": {"es": "Descargar", "en": "Download"},

    # ---- error toasts (code → title/body) ----
    "err.silence.title": {"es": "No se detectó voz", "en": "No speech detected"},
    "err.silence.body": {"es": "Mantén el atajo presionado mientras hablas.",
                         "en": "Hold the shortcut down while you speak."},
    "err.hallucination.title": {"es": "No se detectó voz", "en": "No speech detected"},
    "err.hallucination.body": {"es": "Solo se oyó ruido de fondo. Acércate al micrófono e intenta de nuevo.",
                               "en": "Only background noise. Move closer to the mic and try again."},
    "err.no_key.title": {"es": "Falta la API key", "en": "API key missing"},
    "err.no_key.body": {"es": "Este modelo usa la nube. Añade tu key en Ajustes o cambia a Whisper Turbo local.",
                        "en": "This model uses the cloud. Add your key in Settings or switch to local Whisper Turbo."},
    "err.auth.title": {"es": "API key inválida", "en": "Invalid API key"},
    "err.auth.body": {"es": "Groq rechazó tu key. Revísala en el Hub → Ajustes.",
                      "en": "Groq rejected your key. Check it in Hub → Settings."},
    "err.rate_limit.title": {"es": "Límite de Groq alcanzado", "en": "Groq rate limit reached"},
    "err.rate_limit.body": {"es": "Espera un momento o cambia a Whisper Turbo local en Ajustes.",
                            "en": "Wait a moment or switch to local Whisper Turbo in Settings."},
    "err.offline.title": {"es": "Sin conexión", "en": "No connection"},
    "err.offline.body": {"es": "Groq necesita internet. Cambia a Whisper Turbo local en Ajustes para dictar offline.",
                         "en": "Groq needs the internet. Switch to local Whisper Turbo in Settings to dictate offline."},
    "err.timeout.title": {"es": "Groq tardó demasiado", "en": "Groq timed out"},
    "err.timeout.body": {"es": "La red va lenta. Reintenta o cambia a Whisper Turbo local en Ajustes.",
                         "en": "The network is slow. Retry or switch to local Whisper Turbo in Settings."},
    "err.server.title": {"es": "Groq no responde", "en": "Groq is down"},
    "err.server.body": {"es": "El servicio falló. Reintenta en un momento o usa Whisper Turbo local.",
                        "en": "The service failed. Retry shortly or use local Whisper Turbo."},
    "err.permission.title": {"es": "Falta permiso de Accesibilidad", "en": "Accessibility permission missing"},
    "err.permission.body": {"es": "SFlow no puede escribir en otras apps. Concédelo en Ajustes del sistema.",
                            "en": "SFlow can't type into other apps. Grant it in System Settings."},
    "err.paste_failed.title": {"es": "No se pudo pegar", "en": "Couldn't paste"},
    "err.paste_failed.body": {"es": "Falta el permiso de Accesibilidad. Tu texto está guardado en el historial.",
                              "en": "Accessibility permission missing. Your text is saved in the history."},
    "err.no_selection.title": {"es": "No hay texto seleccionado", "en": "No text selected"},
    "err.no_selection.body": {"es": "Selecciona el texto que quieres transformar y vuelve a intentarlo.",
                              "en": "Select the text you want to transform and try again."},
    "err.db_corrupt.title": {"es": "Historial dañado", "en": "History damaged"},
    "err.db_corrupt.body": {"es": "El archivo de historial estaba corrupto. SFlow empezó uno nuevo y guardó el anterior por si acaso.",
                            "en": "The history file was corrupt. SFlow started a fresh one and kept the old one just in case."},
    "err.recording_capped.title": {"es": "Grabación detenida", "en": "Recording stopped"},
    "err.recording_capped.body": {"es": "Manos libres se detuvo sola al llegar al límite de tiempo. Tu dictado se está procesando.",
                                  "en": "Hands-free stopped itself at the time limit. Your dictation is being processed."},
    "err.model_missing.title": {"es": "Modelo no descargado", "en": "Model not downloaded"},
    "err.model_missing.body": {"es": "Este modelo local aún no está en tu Mac. Descárgalo en Ajustes → Modelo.",
                               "en": "This local model isn't on your Mac yet. Download it in Settings → Model."},
    "err.unknown.title": {"es": "Algo falló", "en": "Something went wrong"},
    "err.unknown.body": {"es": "No se pudo completar el dictado. Revisa sflow.log si se repite.",
                         "en": "Couldn't complete the dictation. Check sflow.log if it repeats."},
}


def resolve_language() -> str:
    """The active 2-letter language. 'auto' follows the system locale."""
    lang = (get_setting("language", "auto") or "auto").strip().lower()
    if lang in LANGUAGES:
        return lang
    try:
        from PyQt6.QtCore import QLocale
        code = QLocale.system().name()[:2].lower()
        return code if code in LANGUAGES else _DEFAULT_LANG
    except Exception:
        return _DEFAULT_LANG


def tr(key: str, **fmt) -> str:
    """Translate ``key`` to the active language, formatting with ``**fmt``."""
    entry = CATALOG.get(key)
    if entry is None:
        return key  # unknown key: return it verbatim rather than crash
    text = entry.get(resolve_language()) or entry.get(_DEFAULT_LANG) or key
    if fmt:
        try:
            return text.format(**fmt)
        except Exception:
            return text
    return text
