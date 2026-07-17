"""Local transcription via parakeet-mlx (NVIDIA Parakeet on Apple MLX).

El motor mas RAPIDO del stack (mismo que usa Handy). Benchmark M4 (voz real es,
12-jul-2026): ~280ms warm en dictados cortos = ~25x realtime, offline, $0.
Trade-off: pierde precision en nombres propios / jerga vs Whisper Turbo, y NO
soporta hint de vocabulario (el diccionario personal se ignora aqui).

Modelo por defecto: mlx-community/parakeet-tdt-0.6b-v3 (multilingue, ~600MB).
El modelo se mantiene RESIDENTE tras el primer load (warm) para latencia minima.
Opcional: `pip install parakeet-mlx` (Apple Silicon).
"""
import io
import os
import tempfile

from core.models import ModelManager, ModelNotDownloaded


class ParakeetTranscriber:
    """parakeet-mlx backend. Lazy-load from a LOCAL path + modelo residente.

    Parakeet ships bundled, so its weights are normally resolved from _MEIPASS;
    in dev they come from the HF cache. Either way it loads from a path via the
    ModelManager, never a bare repo id — no implicit download."""

    def __init__(self, model_id: str = "mlx-community/parakeet-tdt-0.6b-v3",
                 manager: ModelManager | None = None):
        self._model_id = model_id
        self._manager = manager or ModelManager()
        self._model = None
        self._tried_import = False
        self._import_error: str | None = None

    @property
    def available(self) -> bool:
        if not self._tried_import:
            self._tried_import = True
            try:
                import parakeet_mlx  # noqa: F401
            except Exception as e:
                self._import_error = str(e)
        return self._import_error is None

    def is_downloaded(self) -> bool:
        return self._manager.is_available(self._model_id)

    def _weights_path(self) -> str:
        p = self._manager.resolve_path(self._model_id)
        if not p:
            raise ModelNotDownloaded(self._model_id)
        return p

    def _ensure_model(self):
        if self._model is None:
            from parakeet_mlx import from_pretrained
            self._model = from_pretrained(self._weights_path())
        return self._model

    def warm(self):
        """Precarga el modelo (llamar al arranque para que el 1er dictado sea warm).
        No-op if the weights aren't present — no implicit download."""
        if self.available and self.is_downloaded():
            self._ensure_model()

    def transcribe(self, wav_buffer: io.BytesIO, vocabulary_prompt: str = "") -> str:
        # vocabulary_prompt se ignora: Parakeet no acepta hint de vocabulario.
        if not self.available:
            raise RuntimeError(f"parakeet-mlx not available: {self._import_error}")

        wav_buffer.seek(0)
        data = wav_buffer.read()
        if len(data) < 100:
            return ""

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            result = self._ensure_model().transcribe(tmp_path)
            return (getattr(result, "text", "") or "").strip()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @property
    def model_id(self) -> str:
        return self._model_id
