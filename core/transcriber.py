"""Transcription router. Orchestrates the full pipeline:

   audio → (Groq | Local) → smart_commands → LLM cleanup (tone-aware) → text

All post-processing steps are toggleable via settings.json.
"""
import io
import threading
from config import get_setting, get_stt_model
from core.transcriber_groq import GroqTranscriber
from core.transcriber_local import LocalTranscriber
from core.transcriber_parakeet import ParakeetTranscriber
from core.models import ModelNotDownloaded
from core.llm_cleanup import LLMCleanup
from core.smart_commands import apply as apply_smart_commands
from core.dictionary import as_whisper_prompt
from core.context import tone_for_active_app
from core.snippets_matcher import apply as apply_snippets
from core.substitutions import apply as apply_substitutions

# Motores que aprovechan el hint de vocabulario (diccionario personal).
_VOCAB_ENGINES = {"groq", "whisper"}

# The always-on-device fallback: its weights ship inside the bundle.
_PARAKEET_REPO = "mlx-community/parakeet-tdt-0.6b-v3"


def _is_downloaded(backend) -> bool:
    check = getattr(backend, "is_downloaded", None)
    return check() if callable(check) else True


class Transcriber:
    def __init__(self):
        self._groq = GroqTranscriber()
        self._cleanup = LLMCleanup()
        # Cache de backends por clave (engine|model_id) para conservar el modelo
        # residente (warm) entre dictados. Groq se reusa siempre.
        self._backends = {}
        # El warm de arranque (hilo aparte) y el primer dictado pueden entrar a
        # _get_backend a la vez → doble carga del modelo (~1.6 GB). El lock lo evita.
        self._backends_lock = threading.Lock()

    def _get_backend(self, engine: str, model_id: str):
        key = f"{engine}|{model_id}"
        with self._backends_lock:
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
        """Devuelve (backend, engine) segun el modelo activo. Local-first: si el
        motor elegido no esta disponible (MLX no instalado) O sus pesos no estan
        descargados, cae al Parakeet BUNDLEADO (sigue local); Groq queda como
        ultimo recurso (necesita key)."""
        m = get_stt_model()
        engine = m["engine"]
        if engine == "groq":
            return self._groq, "groq"
        backend = self._get_backend(engine, m["model"])
        if getattr(backend, "available", True) and _is_downloaded(backend):
            return backend, engine
        # Local-first fallback to the bundled Parakeet before ever touching the cloud.
        if engine != "parakeet":
            pk = self._get_backend("parakeet", _PARAKEET_REPO)
            if getattr(pk, "available", True) and _is_downloaded(pk):
                return pk, "parakeet"
        return self._groq, "groq"  # last resort — cloud, needs a key

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

    def transcribe_raw(self, wav_buffer: io.BytesIO) -> str:
        """Raw STT with the active local-first backend, no post-processing.

        Command Mode uses this: the voice is an instruction ("hazlo más formal"),
        not dictation to clean — so smart-commands / cleanup / snippets must not
        touch it. Keeping it on the local engine means the audio stays on-device
        (only the LLM transform may reach the cloud, per the configured provider)."""
        backend, engine = self._resolve()
        try:
            return backend.transcribe(wav_buffer, vocabulary_prompt="") or ""
        except ModelNotDownloaded:
            raise
        except Exception:
            if engine != "groq":
                try:
                    wav_buffer.seek(0)
                except Exception:
                    pass
                return self._groq.transcribe(wav_buffer, vocabulary_prompt="") or ""
            raise

    def transcribe(self, wav_buffer: io.BytesIO) -> tuple[str, str]:
        """Returns (final_text, model_id_used)."""
        backend, engine = self._resolve()

        # Hint de vocabulario (diccionario personal): solo Groq + Whisper lo usan.
        # Parakeet lo ignora (no soporta initial_prompt).
        vocab = ""
        if engine in _VOCAB_ENGINES and get_setting("personal_dictionary_enabled", True):
            vocab = as_whisper_prompt()

        try:
            raw = backend.transcribe(wav_buffer, vocabulary_prompt=vocab)
        except ModelNotDownloaded:
            # Honest: the weights vanished mid-run (a rare race — _resolve only
            # returns a downloaded backend). Surface "download it in Ajustes",
            # never a false Groq/no-key error.
            raise
        except Exception as e:
            # A local engine can fail at RUNTIME even when importable — e.g. the
            # one-time Hugging Face model download drops mid-way. `_resolve`'s
            # `available` check only covers import failure, so fall back to Groq
            # here instead of surfacing an error the user can't act on.
            if engine != "groq":
                from core.logger import log
                log(f"local engine '{engine}' failed at runtime ({e}); falling back to Groq", "WARN")
                backend, engine = self._groq, "groq"
                try:
                    wav_buffer.seek(0)
                except Exception:
                    pass
                raw = backend.transcribe(wav_buffer, vocabulary_prompt=vocab)
            else:
                raise
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
