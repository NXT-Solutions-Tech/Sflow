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
    "tray.status_paused": {"es": "SFlow — Pausado", "en": "SFlow — Paused"},
    "tray.pause": {"es": "Pausar SFlow", "en": "Pause SFlow"},
    "tray.model": {"es": "Modelo", "en": "Model"},
    "tray.paste_last": {"es": "Pegar último dictado", "en": "Paste last transcript"},
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
    "filter.all_apps": {"es": "Todas las apps", "en": "All apps"},
    "filter.all_models": {"es": "Todos los modelos", "en": "All models"},
    "filter.all_time": {"es": "Todo el tiempo", "en": "All time"},
    "filter.today": {"es": "Hoy", "en": "Today"},
    "filter.7d": {"es": "Últimos 7 días", "en": "Last 7 days"},
    "filter.30d": {"es": "Últimos 30 días", "en": "Last 30 days"},
    "page.dictionary": {"es": "Diccionario personal", "en": "Personal dictionary"},
    "page.snippets": {"es": "Snippets", "en": "Snippets"},
    "page.settings": {"es": "Ajustes", "en": "Settings"},
    "page.insights": {"es": "Métricas", "en": "Insights"},

    # ---- home dashboard ----
    "home.greet_morning": {"es": "Buenos días", "en": "Good morning"},
    "home.greet_afternoon": {"es": "Buenas tardes", "en": "Good afternoon"},
    "home.greet_evening": {"es": "Buenas noches", "en": "Good evening"},
    "home.sub_today": {"es": "Has dictado {words} palabras hoy.", "en": "You've dictated {words} words today."},
    "home.sub_idle": {"es": "Listo para dictar — mantén Ctrl+Alt.", "en": "Ready to dictate — hold Ctrl+Alt."},
    "home.stat_total": {"es": "transcripciones", "en": "transcriptions"},
    "home.stat_words": {"es": "palabras dictadas", "en": "words dictated"},
    "home.stat_today": {"es": "dictados hoy", "en": "dictations today"},
    "home.streak": {"es": "Racha", "en": "Streak"},
    "home.streak_days": {"es": "{n} días seguidos", "en": "{n} days in a row"},
    "home.streak_day": {"es": "1 día seguido", "en": "1 day in a row"},
    "home.streak_none": {"es": "Empieza tu racha hoy", "en": "Start your streak today"},
    "home.activity_14d": {"es": "Actividad · últimos 14 días", "en": "Activity · last 14 days"},
    "home.shortcuts": {"es": "Atajos", "en": "Shortcuts"},
    "home.sc_dictate": {"es": "Dictado normal", "en": "Normal dictation"},
    "home.sc_handsfree": {"es": "Manos libres", "en": "Hands-free"},
    "home.sc_command": {"es": "Command Mode", "en": "Command Mode"},
    "home.sc_hub": {"es": "Abrir Hub", "en": "Open Hub"},
    "home.latest": {"es": "Último dictado", "en": "Latest dictation"},
    "home.empty_title": {"es": "Aún no has dictado nada", "en": "Nothing dictated yet"},
    "home.empty_hint": {"es": "Mantén Ctrl+Alt y habla — el texto aparece donde esté tu cursor.", "en": "Hold Ctrl+Alt and speak — text lands wherever your cursor is."},

    # ---- insights ----
    "insights.words": {"es": "Palabras totales", "en": "Total words"},
    "insights.wpm": {"es": "Palabras / minuto", "en": "Words / minute"},
    "insights.count": {"es": "Dictados", "en": "Dictations"},
    "insights.streak": {"es": "Racha (días)", "en": "Streak (days)"},
    "insights.per_app": {"es": "Uso por app", "en": "Usage by app"},
    "insights.activity": {"es": "Actividad · últimos 21 días", "en": "Activity · last 21 days"},
    "insights.legend_less": {"es": "menos", "en": "less"},
    "insights.legend_more": {"es": "más", "en": "more"},
    "insights.empty": {"es": "Aún no hay dictados. Dicta algo con Ctrl+Alt.", "en": "No dictations yet. Dictate something with Ctrl+Alt."},

    # ---- common / shared ----
    "common.save": {"es": "Guardar", "en": "Save"},
    "common.cancel": {"es": "Cancelar", "en": "Cancel"},
    "common.add": {"es": "Agregar", "en": "Add"},
    "common.error": {"es": "Error", "en": "Error"},

    # ---- nav / page (transforms) ----
    "nav.transforms": {"es": "Transforms", "en": "Transforms"},
    "page.transforms": {"es": "Transforms", "en": "Transforms"},

    # ---- history ----
    "history.sub": {"es": "Tus transcripciones recientes. Click en una para expandir, ⋮ para acciones.",
                    "en": "Your recent transcriptions. Click one to expand, ⋮ for actions."},
    "history.search": {"es": "Buscar transcripciones…", "en": "Search transcriptions…"},
    "history.empty": {"es": "Nada por aquí todavía", "en": "Nothing here yet"},
    "history.empty_hint": {"es": "Dicta algo presionando Ctrl+Alt.", "en": "Dictate something by holding Ctrl+Alt."},
    "history.no_audio_title": {"es": "Sin audio", "en": "No audio"},
    "history.no_audio_body": {"es": "Este dictado no tiene WAV asociado.", "en": "This dictation has no saved WAV."},
    "history.retranscribing": {"es": "Re-transcribiendo…", "en": "Re-transcribing…"},

    # ---- edit-transcript dialog ----
    "editdlg.hint": {"es": "Corrige el texto. SFlow sugiere automáticamente palabras nuevas (nombres, jerga) para el diccionario.",
                     "en": "Fix the text. SFlow auto-suggests new words (names, jargon) for your dictionary."},

    # ---- dictionary ----
    "dict.sub": {"es": "Una palabra o frase por línea (pista de vocabulario para Whisper: nombres, jerga, términos técnicos).\nPara sustituciones automáticas de texto usa una flecha:  btw -> by the way",
                 "en": "One word or phrase per line (vocabulary hint for Whisper: names, jargon, technical terms).\nFor automatic text substitutions use an arrow:  btw -> by the way"},
    "dict.save_error": {"es": "No se pudo guardar: {err}", "en": "Couldn't save: {err}"},

    # ---- snippets ----
    "snippets.sub": {"es": 'Atajos de voz. Cuando dictes el trigger, SFlow lo reemplaza por la expansión. Ejemplo: di "mi correo" y se pega tu email.',
                     "en": 'Voice shortcuts. When you dictate the trigger, SFlow replaces it with the expansion. Example: say "my email" and your address is pasted.'},
    "snippets.add_header": {"es": "Agregar snippet", "en": "Add snippet"},
    "snippets.trigger_placeholder": {"es": "trigger (ej: mi correo)", "en": "trigger (e.g. my email)"},
    "snippets.expansion_placeholder": {"es": "expansión (lo que se pega cuando digas el trigger)", "en": "expansion (what gets pasted when you say the trigger)"},
    "snippets.empty_fields_title": {"es": "Campos vacíos", "en": "Empty fields"},
    "snippets.empty_fields_body": {"es": "Trigger y expansión son requeridos.", "en": "Trigger and expansion are required."},
    "snippets.empty_title": {"es": "No tienes snippets aún", "en": "No snippets yet"},
    "snippets.empty_hint": {"es": "Agrega uno arriba: di el trigger y SFlow pega la expansión.", "en": "Add one above: say the trigger and SFlow pastes the expansion."},
    "snippets.used": {"es": "· usado {n}×", "en": "· used {n}×"},

    # ---- transforms ----
    "transforms.sub": {"es": "Reescrituras con IA sobre el texto seleccionado. Selecciona texto y aplica con ⌥+1…8.",
                       "en": "AI rewrites over the selected text. Select text and apply with ⌥+1…8."},
    "transforms.name_placeholder": {"es": "Nombre del transform", "en": "Transform name"},
    "transforms.prompt_placeholder": {"es": "Instrucción para el LLM (ej: Reescribe este texto de forma más concisa…)",
                                       "en": "Instruction for the LLM (e.g. Rewrite this text more concisely…)"},
    "transforms.reset": {"es": "Restaurar predeterminados", "en": "Restore defaults"},
    "transforms.save": {"es": "Guardar transforms", "en": "Save transforms"},
    "transforms.saved_title": {"es": "Guardado", "en": "Saved"},
    "transforms.saved_body": {"es": "Transforms actualizados. ⌥+1…8 usan los nuevos prompts.",
                              "en": "Transforms updated. ⌥+1…8 now use the new prompts."},

    # ---- settings: sections + tabs ----
    "settings.tab_general": {"es": "General", "en": "General"},
    "settings.tab_system": {"es": "Sistema", "en": "System"},
    "settings.sec_transcription": {"es": "Transcripción", "en": "Transcription"},
    "settings.sec_cleanup": {"es": "Auto Cleanup", "en": "Auto Cleanup"},
    "settings.sec_text": {"es": "Texto", "en": "Text"},
    "settings.sec_appearance": {"es": "Apariencia", "en": "Appearance"},
    "settings.sec_paste": {"es": "Inserción de texto", "en": "Text insertion"},
    "settings.sec_sound": {"es": "Sonido", "en": "Sound"},
    "settings.sec_behavior": {"es": "Comportamiento", "en": "Behavior"},
    "settings.sec_mouse": {"es": "Hotkey de mouse (opcional)", "en": "Mouse hotkey (optional)"},
    "settings.sec_keys": {"es": "API Keys · macOS Keychain", "en": "API Keys · macOS Keychain"},
    # labels
    "settings.model_label": {"es": "Modelo de transcripción", "en": "Transcription model"},
    "settings.dictlang_label": {"es": "Idioma del dictado", "en": "Dictation language"},
    "settings.mic_label": {"es": "Micrófono / entrada de audio", "en": "Microphone / audio input"},
    "settings.cleanup_label": {"es": "Nivel de limpieza", "en": "Cleanup level"},
    "settings.provider_label": {"es": "Proveedor de limpieza", "en": "Cleanup provider"},
    "settings.theme_label": {"es": "Tema", "en": "Theme"},
    "settings.paste_label": {"es": "Método de pegado", "en": "Paste method"},
    "settings.groq_key_label": {"es": "Groq API Key (STT en la nube + limpieza Llama)", "en": "Groq API Key (cloud STT + Llama cleanup)"},
    "settings.or_key_label": {"es": "OpenRouter API Key (limpieza GLM)", "en": "OpenRouter API Key (GLM cleanup)"},
    "settings.keys_hint": {"es": "Se guardan en el Keychain de macOS. Deja en blanco para conservar la actual.",
                           "en": "Stored in the macOS Keychain. Leave blank to keep the current one."},
    # dictation-language options
    "settings.dl_auto": {"es": "Auto — detecta ES/EN automáticamente", "en": "Auto — detects ES/EN automatically"},
    "settings.dl_es": {"es": "Español", "en": "Spanish"},
    "settings.dl_en": {"es": "English", "en": "English"},
    "settings.mic_default": {"es": "Predeterminado del sistema", "en": "System default"},
    # cleanup options
    "settings.cl_none": {"es": "None — sin limpieza, texto verbatim", "en": "None — no cleanup, verbatim text"},
    "settings.cl_light": {"es": "Light — muletillas + puntuación", "en": "Light — fillers + punctuation"},
    "settings.cl_medium": {"es": "Medium — claridad + concisión", "en": "Medium — clarity + concision"},
    # provider options
    "settings.pr_groq": {"es": "Groq · Llama (nube)", "en": "Groq · Llama (cloud)"},
    "settings.pr_openrouter": {"es": "OpenRouter · GLM (nube)", "en": "OpenRouter · GLM (cloud)"},
    "settings.pr_local": {"es": "Local · Qwen (offline)", "en": "Local · Qwen (offline)"},
    # theme options
    "settings.th_auto": {"es": "Automático — sigue el sistema", "en": "Automatic — follow system"},
    "settings.th_light": {"es": "Claro", "en": "Light"},
    "settings.th_dark": {"es": "Oscuro", "en": "Dark"},
    # paste options
    "settings.pb_keystroke": {"es": "Keystroke — no toca tu portapapeles (recomendado)", "en": "Keystroke — never touches your clipboard (recommended)"},
    "settings.pb_clipboard": {"es": "Clipboard + Cmd+V — sobrescribe el portapapeles", "en": "Clipboard + Cmd+V — overwrites the clipboard"},
    # switches
    "settings.sw_tone": {"es": "Adaptar tono según la app activa (Slack casual, Gmail formal…)", "en": "Adapt tone to the active app (Slack casual, Gmail formal…)"},
    "settings.sw_commands": {"es": 'Comandos de voz ("nueva línea", "punto y aparte", "coma")', "en": 'Voice commands ("new line", "new paragraph", "comma")'},
    "settings.sw_dict": {"es": "Usar diccionario personal como vocabulario", "en": "Use personal dictionary as vocabulary"},
    "settings.sw_subs": {"es": "Sustituciones de texto (btw → by the way)", "en": "Text substitutions (btw → by the way)"},
    "settings.sw_streaming": {"es": "Streaming paste (typing palabra-por-palabra)", "en": "Streaming paste (word-by-word typing)"},
    "settings.sw_sound_start": {"es": "Sonido al empezar a dictar", "en": "Sound when dictation starts"},
    "settings.sw_sound_done": {"es": "Sonido al terminar", "en": "Sound when it finishes"},
    "settings.sw_command_mode": {"es": "Command Mode (Ctrl+Shift hold → transforma selección con voz · el audio se transcribe local; la transformación usa el proveedor de limpieza configurado)",
                                 "en": "Command Mode (Ctrl+Shift hold → transform selection by voice · audio is transcribed locally; the transform uses the configured cleanup provider)"},
    "settings.sw_save_audio": {"es": "Guardar audio para re-transcribir (historial)", "en": "Keep audio for re-transcription (history)"},
    "settings.sw_glass": {"es": "Liquid Glass en la pill (experimental — macOS 26+)", "en": "Liquid Glass on the pill (experimental — macOS 26+)"},
    # mouse options
    "settings.ms_none": {"es": "Ninguno", "en": "None"},
    "settings.ms_middle": {"es": "Click medio (rueda)", "en": "Middle click (wheel)"},
    "settings.ms_x1": {"es": "Botón lateral 1 (Mouse4)", "en": "Side button 1 (Mouse4)"},
    "settings.ms_x2": {"es": "Botón lateral 2 (Mouse5)", "en": "Side button 2 (Mouse5)"},
    # key-status placeholders
    "settings.ks_keychain": {"es": "•••••••• (guardada en Keychain)", "en": "•••••••• (stored in Keychain)"},
    "settings.ks_env": {"es": "•••••••• (desde .env)", "en": "•••••••• (from .env)"},
    "settings.ks_none": {"es": "no configurada", "en": "not set"},
    "settings.relaunch_body": {"es": "Se cerrará y abrirá una nueva instancia. ¿Continuar?",
                               "en": "SFlow will close and reopen a fresh instance. Continue?"},
    # STT model combo labels (data lives in config.STT_MODELS; translated at display)
    "model.whisper-turbo-local": {"es": "Whisper Turbo · LOCAL (mejor precisión, offline)",
                                  "en": "Whisper Turbo · LOCAL (best accuracy, offline)"},
    "model.parakeet-v3": {"es": "Parakeet v3 · LOCAL (más rápido, offline)",
                          "en": "Parakeet v3 · LOCAL (fastest, offline)"},
    "model.groq-turbo": {"es": "Groq · Whisper Turbo (nube, requiere internet)",
                         "en": "Groq · Whisper Turbo (cloud, needs internet)"},

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
