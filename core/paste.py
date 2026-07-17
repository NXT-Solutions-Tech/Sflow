"""Paste text into the foreground app. Two backends:

1. KEYSTROKE (default): CGEventKeyboardSetUnicodeString — inyecta el texto
   directamente como eventos de teclado Unicode. NO toca el clipboard del
   usuario. Más privacy-friendly y más rápido para strings pequeños.

2. CLIPBOARD (fallback): NSPasteboard + Cmd+V. Preserva y restaura el
   clipboard del usuario alrededor del paste, pero hay una ventana (~0.5s)
   donde otro listener podría leer el texto intermedio.

La elección se hace por setting `paste_backend` ("keystroke" | "clipboard").
"""
import time
import subprocess
from config import get_setting
from core.logger import log


_saved_app: str | None = None
_saved_clipboard: str | None = None


def _as_literal(s: str) -> str:
    """Escape a string for safe embedding in an AppleScript string literal —
    strips control chars and escapes backslash + double-quote so a
    maliciously-named frontmost app can't inject AppleScript."""
    s = "".join(c for c in (s or "") if c.isprintable())
    return s.replace("\\", "\\\\").replace('"', '\\"')


# ---------- Focus management ----------
def save_frontmost_app():
    global _saved_app
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


def _restore_focus():
    """Activa la app guardada. SOLO para el path clipboard: Cmd+V va dirigido a
    System Events y necesita la app destino activa. El path keystroke NO debe
    llamar aquí — ver paste_text()."""
    global _saved_app
    if not _saved_app:
        return
    try:
        from AppKit import NSWorkspace, NSRunningApplication
        ws = NSWorkspace.sharedWorkspace()
        # Try to find the saved app by name and activate it natively
        for app in ws.runningApplications():
            if str(app.localizedName() or "") == _saved_app:
                # NSApplicationActivateIgnoringOtherApps = 1 << 1
                try:
                    app.activateWithOptions_(1 << 1)
                    time.sleep(0.08)
                    return
                except Exception:
                    break
    except Exception:
        pass
    # Fallback: AppleScript
    try:
        subprocess.run(
            ["osascript", "-e", f'tell application "{_as_literal(_saved_app)}" to activate'],
            check=True, timeout=2,
        )
        time.sleep(0.12)
    except Exception:
        pass


# ---------- Clipboard (legacy path) ----------
def _clipboard_read() -> str:
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString
        pb = NSPasteboard.generalPasteboard()
        val = pb.stringForType_(NSPasteboardTypeString)
        return str(val) if val else ""
    except Exception:
        try:
            r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=1)
            return r.stdout
        except Exception:
            return ""


def _clipboard_write(text: str):
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSPasteboardTypeString)
    except Exception:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def _cmd_v() -> bool:
    """Cmd+V vía System Events. El timeout no es opcional: sin él, un osascript
    colgado (p.ej. esperando un prompt de permisos) cuelga al hilo llamante
    para siempre."""
    try:
        subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
            check=True, timeout=2,
        )
        return True
    except Exception as e:
        log(f"paste: Cmd+V failed ({e})", level="ERROR")
        return False


def _paste_via_clipboard(text: str) -> bool:
    global _saved_clipboard
    _saved_clipboard = _clipboard_read()
    _clipboard_write(text)
    _restore_focus()
    ok = _cmd_v()
    # Restore user's original clipboard after brief delay so paste completes
    if _saved_clipboard is not None:
        def _restore():
            time.sleep(0.5)
            try:
                _clipboard_write(_saved_clipboard)
            except Exception:
                pass
        import threading
        threading.Thread(target=_restore, daemon=True).start()
    return ok


# ---------- Keystroke injection (default path) ----------
def _type_via_cgevent(text: str) -> bool:
    """Synthesize Unicode keyboard events. Returns True on success, False if CGEvent unavailable."""
    try:
        from Quartz import (
            CGEventCreateKeyboardEvent,
            CGEventKeyboardSetUnicodeString,
            CGEventPost,
            kCGHIDEventTap,
        )
    except Exception as e:
        log(f"paste: CGEvent unavailable ({e}) — falling back to clipboard", level="ERROR")
        return False

    # Chunk the text to avoid OS rate-limiting. Experimentally 20 chars per
    # event works well on macOS; some apps drop characters on very large events.
    CHUNK = 20
    i = 0
    n = len(text)
    while i < n:
        piece = text[i:i + CHUNK]
        # Key DOWN with unicode payload
        down = CGEventCreateKeyboardEvent(None, 0, True)
        CGEventKeyboardSetUnicodeString(down, len(piece), piece)
        CGEventPost(kCGHIDEventTap, down)
        # Key UP (mirror)
        up = CGEventCreateKeyboardEvent(None, 0, False)
        CGEventKeyboardSetUnicodeString(up, len(piece), piece)
        CGEventPost(kCGHIDEventTap, up)
        i += CHUNK
        if i < n:
            time.sleep(0.004)  # brief pause so apps flush characters
    return True


# ---------- Public API ----------
def paste_text(text: str) -> bool:
    """Insert text into the saved frontmost app. Routes via keystroke by default.

    Returns whether the text was delivered. The caller MUST honour it: the
    clipboard path reports failure by returning False (osascript refused, TCC
    revoked), not by raising, so discarding this flashes a green check over a
    paste that never landed.
    """
    global _saved_app
    if not text:
        _saved_app = None
        return True

    backend = get_setting("paste_backend", "keystroke")
    streaming = get_setting("streaming_paste_enabled", False)

    # OJO: el path keystroke NO restaura el foco. SFlow corre como accessory y
    # la pill es un NonactivatingPanel, así que la app destino ya es frontmost y
    # los CGEvent aterrizan solos. Activarla era un app-switch redundante (el
    # flash) y, peor, si el usuario cambió de ventana durante la transcripción
    # (~950ms) le arrancaba el foco de vuelta y escribía en la app vieja.
    # El path clipboard sí lo necesita y lo hace él mismo en
    # _paste_via_clipboard() — Cmd+V va vía System Events a la app activa.
    ok = True
    if backend == "keystroke":
        if streaming and len(text) > 40:
            # For "streaming" feel with keystroke, we send chars in bursts
            parts = text.split(" ")
            for i, p in enumerate(parts):
                chunk = p + (" " if i < len(parts) - 1 else "")
                if not _type_via_cgevent(chunk):
                    # Fallback mid-operation
                    ok = _paste_via_clipboard(text[sum(len(x) + 1 for x in parts[:i]):])
                    break
                time.sleep(0.02)
        else:
            ok = _type_via_cgevent(text)
            if not ok:
                ok = _paste_via_clipboard(text)
    else:
        ok = _paste_via_clipboard(text)

    _saved_app = None
    return ok


def paste_last_transcript(text: str):
    """Alternative entry point for the 'paste last' hotkey — no focus restore
    because the user invoked it from the app they want the paste in."""
    backend = get_setting("paste_backend", "keystroke")
    if backend == "keystroke":
        if not _type_via_cgevent(text):
            _clipboard_write(text)
            _cmd_v()
    else:
        _clipboard_write(text)
        _cmd_v()
