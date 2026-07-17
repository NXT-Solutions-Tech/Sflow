"""Local transcription via mlx-whisper (Whisper on Apple MLX).

Benchmark M4 / voz real es (12-jul-2026), whisper-large-v3-turbo:
  ~950ms warm (10s audio) — mejor precision del stack, WER 2.9%, offline, $0.
  mlx-whisper cachea el modelo cargado por repo => llamadas repetidas van warm.

Opcional: `pip install mlx-whisper` (Apple Silicon).
"""
import io
import tempfile
import os
from config import LOCAL_MODEL_ID, get_stt_language
from core.models import ModelManager, ModelNotDownloaded


class LocalTranscriber:
    """mlx-whisper backend. Lazy-loads the model from a LOCAL path only.

    model_id es parametrizable (whisper-large-v3-turbo por defecto) para que el
    router pueda ofrecer distintos tamanos de Whisper desde Ajustes. It never
    downloads implicitly: the weights come from the ModelManager (bundle or HF
    cache), and a missing model raises ModelNotDownloaded so the UI can offer the
    download instead of the pill hanging on a silent 1.6GB fetch.
    """

    def __init__(self, model_id: str = LOCAL_MODEL_ID, manager: ModelManager | None = None):
        self._model_id = model_id
        self._manager = manager or ModelManager()
        self._tried_import = False
        self._import_error: str | None = None

    @property
    def available(self) -> bool:
        if not self._tried_import:
            try:
                import mlx_whisper  # noqa: F401
                self._tried_import = True
            except Exception as e:
                self._tried_import = True
                self._import_error = str(e)
                return False
        return self._import_error is None

    def is_downloaded(self) -> bool:
        return self._manager.is_available(self._model_id)

    def _weights_path(self) -> str:
        """Local path to the weights, or raise ModelNotDownloaded — never a
        repo id, so mlx-whisper can't kick off a silent download."""
        p = self._manager.resolve_path(self._model_id)
        if not p:
            raise ModelNotDownloaded(self._model_id)
        return p

    def warm(self):
        """Precarga el modelo en un audio de silencio para dejarlo residente.
        No-op if the weights aren't downloaded — warming must not trigger a fetch."""
        if not self.available or not self.is_downloaded():
            return
        import mlx_whisper
        import numpy as np
        try:
            mlx_whisper.transcribe(
                np.zeros(1600, dtype=np.float32),  # 0.1s de silencio
                path_or_hf_repo=self._weights_path(),
                language=get_stt_language(),
                temperature=0.0,
            )
        except Exception:
            pass

    def transcribe(self, wav_buffer: io.BytesIO, vocabulary_prompt: str = "") -> str:
        if not self.available:
            raise RuntimeError(f"mlx-whisper not available: {self._import_error}")

        path = self._weights_path()  # raises ModelNotDownloaded if missing

        import mlx_whisper

        wav_buffer.seek(0)
        data = wav_buffer.read()
        if len(data) < 100:
            return ""

        # mlx-whisper expects path or array — use temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        try:
            kwargs = {
                "path_or_hf_repo": path,
                "language": get_stt_language(),  # None = autodeteccion
                "temperature": 0.0,
            }
            if vocabulary_prompt:
                kwargs["initial_prompt"] = vocabulary_prompt
            result = mlx_whisper.transcribe(tmp_path, **kwargs)
            return (result.get("text") or "").strip()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @property
    def model_id(self) -> str:
        return self._model_id
