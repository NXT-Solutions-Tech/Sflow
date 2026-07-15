"""Transcription router. Orchestrates the full pipeline:

   audio → (Groq | Local) → smart_commands → LLM cleanup (tone-aware) → text

All post-processing steps are toggleable via settings.json.
"""
import io
from config import get_setting, get_stt_model
from core.transcriber_groq import GroqTranscriber
from core.transcriber_local import LocalTranscriber
from core.transcriber_parakeet import ParakeetTranscriber
from core.llm_cleanup import LLMCleanup
from core.smart_commands import apply as apply_smart_commands
from core.dictionary import as_whisper_prompt
from core.context import tone_for_active_app
from core.snippets_matcher import apply as apply_snippets
from core.substitutions import apply as apply_substitutions

# Motores que aprovechan el hint de vocabulario (diccionario personal).
_VOCAB_ENGINES = {"groq", "whisper"}


class Transcriber:
    def __init__(self):
        self._groq = GroqTranscriber()
        self._cleanup = LLMCleanup()
        # Cache de backends por clave (engine|model_id) para conservar el modelo
        # residente (warm) entre dictados. Groq se reusa siempre.
        self._backends = {}

    def _get_backend(self, engine: str, model_id: str):
        key = f"{engine}|{model_id}"
        b = self._backends.get(key)
        if b is None:
            if engine == "parakeet":
                b = ParakeetTranscriber(model_id)
            elif engine == "whisper":
                b = LocalTranscriber(model_id)
            else:
                b = self._groq
            self._backends[key] = b
        return b

    def _resolve(self):
        """Devuelve (backend, engine) segun el modelo activo, con fallback a Groq
        si el motor local no esta disponible en runtime (MLX no instalado)."""
        m = get_stt_model()
        engine = m["engine"]
        if engine == "groq":
            return self._groq, "groq"
        backend = self._get_backend(engine, m["model"])
        if getattr(backend, "available", True):
            return backend, engine
        return self._groq, "groq"  # fallback silencioso

    def _pick_backend(self):
        return self._resolve()[0]

    def warm_active(self):
        """Precarga el modelo local activo (llamar al arranque / al cambiarlo)."""
        backend, engine = self._resolve()
        if engine in ("whisper", "parakeet"):
            try:
                backend.warm()
            except Exception:
                pass

    def transcribe(self, wav_buffer: io.BytesIO) -> tuple[str, str]:
        """Returns (final_text, model_id_used)."""
        backend, engine = self._resolve()

        # Hint de vocabulario (diccionario personal): solo Groq + Whisper lo usan.
        # Parakeet lo ignora (no soporta initial_prompt).
        vocab = ""
        if engine in _VOCAB_ENGINES and get_setting("personal_dictionary_enabled", True):
            vocab = as_whisper_prompt()

        raw = backend.transcribe(wav_buffer, vocabulary_prompt=vocab)
        if not raw:
            return "", backend.model_id

        # Smart commands — regex pass, cheap
        if get_setting("smart_commands_enabled", True):
            raw = apply_smart_commands(raw)

        # LLM cleanup — Auto Cleanup levels (none/light/medium), tone-aware
        level = get_setting("auto_cleanup_level", "none")
        if level != "none":
            tone = "default"
            if get_setting("context_aware_tone", True):
                try:
                    tone = tone_for_active_app()
                except Exception:
                    tone = "default"
            raw = self._cleanup.clean(raw, tone=tone, level=level)

        # Text substitutions (btw -> by the way) from the personal dictionary
        if get_setting("text_substitutions_enabled", True):
            try:
                raw = apply_substitutions(raw)
            except Exception:
                pass

        # Snippets — run LAST so expansions are inserted verbatim, not cleaned
        if get_setting("snippets_enabled", True):
            try:
                raw = apply_snippets(raw)
            except Exception:
                pass

        return raw.strip(), backend.model_id
