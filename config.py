import os
import sys
import json


def _get_resource_dir() -> str:
    """Read-only bundled assets (logo, etc). PyInstaller puts them in sys._MEIPASS."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _get_data_dir() -> str:
    """Writable user data (DB, .env). In bundle → ~/Library/Application Support/SFlow/."""
    if getattr(sys, "frozen", False):
        return os.path.expanduser("~/Library/Application Support/SFlow")
    return os.path.dirname(os.path.abspath(__file__))


_RESOURCE_DIR = _get_resource_dir()
_DATA_DIR = _get_data_dir()

if getattr(sys, "frozen", False):
    os.makedirs(_DATA_DIR, exist_ok=True)

# NOTE: the .env is deliberately NOT loaded into os.environ (no python-dotenv).
# core/secrets.py parses it into a process-private dict instead, so the key never
# leaks to the numba/librosa spawn workers that re-exec this binary.

# --- Settings file (runtime-mutable via UI) ---
SETTINGS_PATH = os.path.join(_DATA_DIR, "settings.json")


def _default_settings() -> dict:
    return {
        # Apariencia visual. "auto" sigue el modo claro/oscuro del sistema macOS;
        # "light" | "dark" fuerzan un tema. Ver ui/theme.py.
        "theme": "auto",
        # Onboarding wizard: version last completed (0 = never). Bumping
        # ONBOARDING_VERSION in core/onboarding.py re-runs it. `snooze_until` is
        # a unix ts that suppresses the re-prompt after a revoked permission, so
        # a user who chose "Ahora no" isn't nagged on every launch.
        "onboarding_seen_version": 0,
        "onboarding_snooze_until": 0,
        # Modelo de transcripcion activo. Ver STT_MODELS (abajo) para el catalogo.
        # Default: Whisper Turbo LOCAL (mejor precision es + offline, gana a Groq en
        # latencia y privacidad segun benchmark M4 12-jul-2026). Fallback a groq si
        # el motor MLX no esta disponible en runtime.
        "stt_model": "whisper-turbo-local",
        "stt_language": "auto",  # "auto" = autodeteccion (ES/EN/...); o codigo ISO como "es"/"en" para forzar
        "auto_cleanup_level": "none",  # "none" | "light" | "medium" (M2 Auto Cleanup). none = sin LLM.
        # NOTE: legacy keys transcribe_backend / llm_cleanup_enabled are NOT defaults
        # anymore. load_settings() still migrates them off an existing file (it reads
        # `loaded`, not defaults), but a fresh install never carries the dead keys.
        "llm_cleanup_provider": "groq",  # "groq" (Llama) | "openrouter" (GLM). Default groq = comportamiento actual, GLM es opt-in.
        "openrouter_cleanup_model": "z-ai/glm-4.7-flash",  # slug OpenRouter para el proveedor GLM (verificar vigencia)
        "context_aware_tone": True,
        "smart_commands_enabled": True,
        "personal_dictionary_enabled": True,
        "text_substitutions_enabled": True,  # "btw -> by the way" desde el diccionario (M3)
        "input_device": "",  # "" = microfono predeterminado del sistema; si no, nombre exacto del dispositivo

        "liquid_glass_enabled": False,
        "streaming_paste_enabled": False,
        "mouse_button_hotkey": None,  # None | "middle" | "x1" | "x2"
        # Opt-in: Command Mode sends the audio AND the selected text to the cloud,
        # so it stays off until the user turns it on (Hub -> Ajustes).
        "command_mode_enabled": False,
        "paste_backend": "keystroke",  # "keystroke" | "clipboard"
        "save_audio_for_retry": True,
        "sound_on_start": False,
        "sound_on_done": False,
        "snippets_enabled": True,
        "transform_prompts": [
            {"label": "Más conciso", "prompt": "Haz este texto más conciso preservando el significado clave."},
            {"label": "Más formal", "prompt": "Reescribe este texto en tono formal profesional."},
            {"label": "Más casual", "prompt": "Reescribe este texto en tono casual amigable."},
            {"label": "Traducir a inglés", "prompt": "Traduce este texto a inglés natural."},
            {"label": "Bullet points", "prompt": "Convierte este texto en una lista de bullet points concisos."},
            {"label": "Corregir ortografía", "prompt": "Corrige solo errores ortográficos y de puntuación, preserva exactamente el resto."},
            {"label": "Expandir idea", "prompt": "Expande esta idea en un párrafo completo y bien estructurado."},
            {"label": "Resumir", "prompt": "Resume este texto en 1-2 oraciones."},
        ],
    }


def load_settings() -> dict:
    defaults = _default_settings()
    if not os.path.exists(SETTINGS_PATH):
        return defaults
    try:
        with open(SETTINGS_PATH) as f:
            loaded = json.load(f)
        defaults.update(loaded)
        # --- Migracion legacy: transcribe_backend -> stt_model ---
        # Si el settings viejo trae transcribe_backend pero no stt_model explicito,
        # mapeamos: "groq" -> groq-turbo, "local" -> whisper (el local historico).
        if "stt_model" not in loaded and "transcribe_backend" in loaded:
            defaults["stt_model"] = (
                "groq-turbo" if loaded["transcribe_backend"] == "groq" else "whisper-turbo-local"
            )
        # --- Migracion legacy: llm_cleanup_enabled (bool) -> auto_cleanup_level ---
        if "auto_cleanup_level" not in loaded and "llm_cleanup_enabled" in loaded:
            defaults["auto_cleanup_level"] = "light" if loaded["llm_cleanup_enabled"] else "none"
        return defaults
    except Exception:
        return defaults


def save_settings(data: dict):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(data, f, indent=2)


_SETTINGS = load_settings()


def get_setting(key: str, default=None):
    return _SETTINGS.get(key, default)


def set_setting(key: str, value):
    _SETTINGS[key] = value
    save_settings(_SETTINGS)


# --- Groq API ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "whisper-large-v3-turbo"
LLM_CLEANUP_MODEL = "llama-3.3-70b-versatile"  # mejor fidelidad que 8b (~300-500ms vs 100-200ms)
WHISPER_LANGUAGE = "es"  # LEGACY: idioma historico. El STT ahora usa get_stt_language() (default autodeteccion).


def get_stt_language():
    """Codigo ISO de idioma para STT, o None para autodeteccion (setting 'stt_language'=='auto')."""
    lang = (get_setting("stt_language", "auto") or "auto").strip().lower()
    return None if lang == "auto" else lang

# --- OpenRouter API (proveedor alternativo de limpieza LLM, default GLM) ---
# Se activa poniendo llm_cleanup_provider="openrouter" (Ajustes). Fail-open: si no hay
# key o la red falla, la transcripcion cruda se pega igual. El slug GLM puede cambiar
# entre releases — verificar en https://openrouter.ai/models antes de empaquetar.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_CLEANUP_MODEL = "z-ai/glm-4.7-flash"  # rapido y ~8x mas barato que glm-4.6, ideal para dictado
OPENROUTER_TIMEOUT = 8.0

# --- Catalogo de modelos STT seleccionables desde la app (Ajustes) ---
# Benchmark M4 / 16GB / voz real es (12-jul-2026), latencia warm mediana + WER:
#   Parakeet v3  : ~280ms  · WER 4.3% · el mas RAPIDO (motor de Handy), pierde en nombres propios
#   Whisper Turbo: ~950ms  · WER 2.9% · MEJOR precision, acierta jerga, usa diccionario personal
#   Groq (nube)  : ~1.4-2.7s · WER 2.9% · misma precision pero mas lento (red) + depende de internet
# engine: "groq" | "whisper" (mlx-whisper) | "parakeet" (parakeet-mlx)
STT_MODELS = [
    {
        "id": "whisper-turbo-local",
        "label": "Whisper Turbo · LOCAL (mejor precision, offline)",
        "engine": "whisper",
        "model": "mlx-community/whisper-large-v3-turbo",
        "local": True,
    },
    {
        "id": "parakeet-v3",
        "label": "Parakeet v3 · LOCAL (mas rapido, offline)",
        "engine": "parakeet",
        "model": "mlx-community/parakeet-tdt-0.6b-v3",
        "local": True,
    },
    {
        "id": "groq-turbo",
        "label": "Groq · Whisper Turbo (nube, requiere internet)",
        "engine": "groq",
        "model": "whisper-large-v3-turbo",
        "local": False,
    },
]

_STT_BY_ID = {m["id"]: m for m in STT_MODELS}


def get_stt_model() -> dict:
    """Devuelve el dict del modelo STT activo (fallback a groq-turbo)."""
    return _STT_BY_ID.get(get_setting("stt_model", "whisper-turbo-local"), _STT_BY_ID["groq-turbo"])


# Back-compat: algunos modulos aun leen LOCAL_MODEL_ID directo.
LOCAL_MODEL_ID = "mlx-community/whisper-large-v3-turbo"

# --- Audio ---
SAMPLE_RATE = 16000
CHANNELS = 1
AUDIO_DTYPE = "int16"
BLOCK_SIZE = 1024
# Hands-free recording runs unattended until the user taps Ctrl again. A stuck
# session (they forgot, walked away) would record forever and hold the mic — cap
# it and auto-stop with a toast. Hold-to-talk is self-limiting (finger on key).
RECORDING_CAP_SECONDS = 5 * 60

# --- UI ---
PILL_WIDTH_IDLE = 34
PILL_WIDTH_RECORDING = 112
PILL_WIDTH_STATUS = 52
PILL_HEIGHT = 34
PILL_OPACITY = 0.90
PILL_CORNER_RADIUS = 17
PILL_MARGIN_BOTTOM = 14
LOGO_SIZE = 22

LOGO_PATH = os.path.join(_RESOURCE_DIR, "logo_small.png")

# --- Audio Visualizer ---
NUM_BARS = 20
VIZ_FPS = 60
BAR_DECAY = 0.85
# Fine-tune knob para el visualizer dB-scaled. ~1.0 = neutro. Subir si las
# barras se ven muy timidas, bajar si saturan. Ya NO es multiplicador raw
# de FFT (eso se reescribio en ui/audio_visualizer.py).
BAR_GAIN = 2.3

# --- Hotkey ---
DOUBLE_TAP_INTERVAL = 0.4
# Ctrl held longer than this is a "hold", not a "tap" — protects against
# accidentally counting a long Ctrl press as part of a double-tap.
CTRL_TAP_MAX_DURATION = 0.25

# --- Database (writable user data) ---
DB_PATH = os.path.join(_DATA_DIR, "transcriptions.db")
DICTIONARY_PATH = os.path.join(_DATA_DIR, "dictionary.txt")
AUDIO_DIR = os.path.join(_DATA_DIR, "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

APP_DATA_DIR = _DATA_DIR
