import io
import os
from groq import Groq
from config import GROQ_MODEL, get_stt_language


_HALLUCINATION_MARKERS = (
    "gracias por ver el video",
    "gracias por ver este video",
    "gracias por ver.",
    "subtitulado por la comunidad",
    "subtítulos por la comunidad",
    "subtitulos realizados por la comunidad",
    "subtítulos realizados por la comunidad",
    "amara.org",
    "suscríbete al canal",
    "suscribete al canal",
    "thank you for watching",
    "thanks for watching",
    "please subscribe",
    "see you next time",
    "estoy listo para ayudarte",
    "¿qué transcripción de voz necesitas",
    "que transcripcion de voz necesitas",
)


def _is_hallucination(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in _HALLUCINATION_MARKERS)


class GroqTranscriber:
    """Cloud transcription via Groq Whisper Large v3 Turbo."""

    def __init__(self):
        self._client = None

    def _get_client(self) -> Groq:
        if self._client is None:
            key = os.getenv("GROQ_API_KEY", "")
            if not key:
                raise ValueError("GROQ_API_KEY not configured")
            self._client = Groq(api_key=key, timeout=10.0)
        return self._client

    def transcribe(self, wav_buffer: io.BytesIO, vocabulary_prompt: str = "") -> str:
        wav_buffer.seek(0)
        data = wav_buffer.read()
        if len(data) < 100:
            return ""
        kwargs = dict(
            file=("recording.wav", data),
            model=GROQ_MODEL,
            response_format="text",
            temperature=0.0,
        )
        lang = get_stt_language()
        if lang:  # None = autodeteccion → omitir el parametro
            kwargs["language"] = lang
        if vocabulary_prompt:
            kwargs["prompt"] = vocabulary_prompt
        transcription = self._get_client().audio.transcriptions.create(**kwargs)
        text = transcription.strip() if isinstance(transcription, str) else str(transcription).strip()
        if _is_hallucination(text):
            return ""
        return text

    @property
    def model_id(self) -> str:
        return GROQ_MODEL
