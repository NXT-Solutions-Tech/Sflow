"""File logger — writes to ~/Library/Application Support/SFlow/sflow.log.

Bundled .app has no stdout/stderr visible to the user, so any error path
that matters MUST log here or it disappears into the void.
"""
import os
import datetime
import traceback
from config import APP_DATA_DIR

LOG_PATH = os.path.join(APP_DATA_DIR, "sflow.log")
_MAX_BYTES = 1_000_000  # rotate at ~1 MB so the log never grows unbounded


def _rotate_if_needed():
    try:
        if os.path.getsize(LOG_PATH) > _MAX_BYTES:
            # Keep one previous generation (sflow.log.1), overwrite older.
            os.replace(LOG_PATH, LOG_PATH + ".1")
    except OSError:
        pass


def log(msg: str, level: str = "INFO"):
    try:
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        _rotate_if_needed()
        with open(LOG_PATH, "a") as f:
            f.write(f"[{ts}] {level:5s} {msg}\n")
    except Exception:
        pass


def log_exc(msg: str, exc: BaseException):
    try:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        log(f"{msg}\n{tb}", level="ERROR")
    except Exception:
        pass
