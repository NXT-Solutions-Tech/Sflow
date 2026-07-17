"""Optional start/done chirps.

Off by default (settings ``sound_on_start`` / ``sound_on_done``). The toggles
existed in the Hub but nothing ever played — this makes them real. Plays a macOS
system sound via ``afplay`` in a daemon thread so audio never blocks or delays
the dictation flow.
"""
import os
import subprocess
import threading

from config import get_setting

_SYSTEM_SOUNDS = "/System/Library/Sounds"
# Subtle, distinct system sounds: a soft tick when recording opens, a brighter
# note when the transcript lands.
_START_SOUND = os.path.join(_SYSTEM_SOUNDS, "Tink.aiff")
_DONE_SOUND = os.path.join(_SYSTEM_SOUNDS, "Glass.aiff")


def _play(path: str):
    def _run():
        try:
            subprocess.run(
                ["afplay", path], check=False, timeout=5,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def play_start():
    if get_setting("sound_on_start", False):
        _play(_START_SOUND)


def play_done():
    if get_setting("sound_on_done", False):
        _play(_DONE_SOUND)
