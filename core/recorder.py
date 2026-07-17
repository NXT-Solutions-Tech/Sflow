import io
import wave
import queue
import time
import numpy as np
import sounddevice as sd
from config import SAMPLE_RATE, CHANNELS, AUDIO_DTYPE, BLOCK_SIZE, get_setting
from core.logger import log


def list_input_devices() -> list[dict]:
    """Dispositivos con canales de entrada: [{'index': int, 'name': str}]."""
    devices = []
    try:
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                devices.append({"index": i, "name": d["name"]})
    except Exception:
        pass
    return devices


def _resolve_input_device():
    """Traduce el setting 'input_device' (nombre) a un index de sounddevice.
    Devuelve None (= predeterminado del sistema) si esta vacio o no se encuentra."""
    name = (get_setting("input_device", "") or "").strip()
    if not name:
        return None
    for d in list_input_devices():
        if d["name"] == name:
            return d["index"]
    return None  # dispositivo desconectado -> caer al predeterminado (fail-safe)


class AudioRecorder:
    def __init__(self):
        self.audio_queue = queue.Queue()  # For UI visualization
        self.frames: list[np.ndarray] = []
        self.stream: sd.InputStream | None = None
        self.is_recording = False
        self._start_time = 0.0
        # Set by the audio callback when PortAudio reports an error status
        # (overflow/underflow/etc). Reset on each start(); surfaced so the next
        # start() knows to open a clean stream rather than reuse a wedged one.
        self.stream_error = False
        self._last_status = None

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            self._note_status(status)
        self.audio_queue.put(indata.copy())
        self.frames.append(indata.copy())

    def _note_status(self, status):
        # Log once per distinct status within a recording — over/underflows can
        # fire every block and would otherwise flood the log.
        self.stream_error = True
        s = str(status)
        if s != self._last_status:
            self._last_status = s
            log(f"audio stream status: {s}", "WARN")

    def elapsed(self) -> float:
        """Wall-clock seconds since start(), or 0 if not recording. Drives the
        hands-free recording cap in the controller."""
        if not self.is_recording or not self._start_time:
            return 0.0
        return time.time() - self._start_time

    def start(self):
        self.frames.clear()
        # Drain any old data from the queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        # A previous stop() that raised could leave a stream dangling; close it
        # before opening a new one so PortAudio streams never stack up.
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        self.stream_error = False
        self._last_status = None
        self.is_recording = True
        self._start_time = time.time()

        def _open(device):
            return sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=AUDIO_DTYPE,
                blocksize=BLOCK_SIZE,
                callback=self._callback,
                device=device,
            )

        device = _resolve_input_device()
        try:
            self.stream = _open(device)
            self.stream.start()
        except Exception as e:
            # Dispositivo elegido no disponible/incompatible -> predeterminado (nunca bloquea).
            if device is not None:
                print(f"Audio device {device!r} fallo ({e}); usando predeterminado")
                self.stream = _open(None)
                self.stream.start()
            else:
                raise

    def stop(self) -> float:
        """Stop recording and return duration in seconds.

        Guarded end to end: a PortAudio error in stop()/close() must not leave
        the stream dangling (start() would then stack a second one) nor propagate
        into the release handler that computes duration and kicks off transcription.
        The stream reference is cleared FIRST so a failing close() can't strand it."""
        self.is_recording = False
        duration = time.time() - self._start_time if self._start_time else 0.0
        stream, self.stream = self.stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as e:
                log(f"recorder.stop failed ({e})", "ERROR")
                self.stream_error = True
        return duration

    def get_wav_buffer(self) -> io.BytesIO:
        """Convert recorded frames to in-memory WAV buffer."""
        if not self.frames:
            return io.BytesIO()
        audio_data = np.concatenate(self.frames, axis=0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data.tobytes())
        buf.seek(0)
        return buf

    def save_wav_to(self, path: str) -> str | None:
        """Write the current recording to disk at `path`. Returns path on success."""
        if not self.frames:
            return None
        audio_data = np.concatenate(self.frames, axis=0)
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data.tobytes())
        return path

    def get_duration(self) -> float:
        if not self.frames:
            return 0.0
        total_samples = sum(f.shape[0] for f in self.frames)
        return total_samples / SAMPLE_RATE
