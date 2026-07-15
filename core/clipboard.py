import subprocess
import time
from config import get_setting

_saved_app: str | None = None


def _as_literal(s: str) -> str:
    """Escape a string for safe embedding in an AppleScript string literal.
    Strips control chars (which would break out of the literal / inject new
    statements) and escapes backslash + double-quote. Guards against a
    maliciously-named frontmost app injecting AppleScript."""
    s = "".join(c for c in (s or "") if c.isprintable())
    return s.replace("\\", "\\\\").replace('"', '\\"')


def save_frontmost_app():
    """Save the currently focused application before recording starts."""
    global _saved_app
    # Prefer NSWorkspace (faster, no subprocess)
    try:
        from AppKit import NSWorkspace
        active = NSWorkspace.sharedWorkspace().frontmostApplication()
        if active is not None:
            name = str(active.localizedName() or "")
            if name and name != "SFlow":
                _saved_app = name
                return
    except Exception:
        pass
    # Fallback: AppleScript
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of first process whose frontmost is true'],
            capture_output=True, text=True, timeout=2,
        )
        name = result.stdout.strip()
        if name and name != "SFlow":
            _saved_app = name
    except Exception:
        pass


def _copy_to_clipboard(text: str):
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSPasteboardTypeString)
    except Exception:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def _restore_focus():
    global _saved_app
    if not _saved_app:
        return
    try:
        subprocess.run(
            ["osascript", "-e", f'tell application "{_as_literal(_saved_app)}" to activate'],
            check=True, timeout=2,
        )
        time.sleep(0.12)
    except Exception:
        pass


def _cmd_v():
    subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
        check=True,
    )


def paste_text(text: str):
    """Copy text to clipboard and paste into the previously active app.

    If streaming_paste_enabled, paste word-by-word for "live typing" UX.
    """
    global _saved_app

    streaming = get_setting("streaming_paste_enabled", False)

    if not streaming or len(text) < 40:
        _copy_to_clipboard(text)
        _restore_focus()
        _cmd_v()
        _saved_app = None
        return

    # Streaming paste: restore focus once, then paste chunks with tiny delay.
    _restore_focus()
    # Split on spaces but keep newlines intact
    parts = []
    buf = ""
    for ch in text:
        buf += ch
        if ch == " " or ch == "\n":
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)

    # Group into chunks of ~3 words to reduce paste count
    chunk_size = 3
    chunks = ["".join(parts[i:i + chunk_size]) for i in range(0, len(parts), chunk_size)]

    for chunk in chunks:
        _copy_to_clipboard(chunk)
        _cmd_v()
        time.sleep(0.025)  # ~25ms between chunks → ~40 cps, feels natural

    _saved_app = None
