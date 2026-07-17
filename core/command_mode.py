"""Command Mode: select text → hotkey → speak a command → LLM transforms selection.

Example:
  1. User selects "this text is too long and rambling"
  2. Holds Ctrl+Shift hotkey, says "hazlo más conciso"
  3. Releases. SFlow grabs the selection via Cmd+C, sends selection + voice
     command to Llama, pastes the result back (Cmd+V) replacing the selection.

If no selection exists, we treat the voice as a freeform Llama query and
paste the response where the cursor is.
"""
import os
import time
import subprocess
from groq import Groq
from config import LLM_CLEANUP_MODEL
from core.logger import log
from core.token_budget import max_tokens_for


_COMMAND_SYSTEM = """Eres un asistente que transforma texto según instrucciones del usuario.

Reglas críticas:
- Devuelve SOLO el texto transformado, sin comentarios ni explicaciones
- NO uses markdown salvo que la instrucción lo pida explícitamente
- Preserva el idioma del texto original a menos que la instrucción pida traducir
- Si la instrucción no es clara, haz la interpretación más razonable
- NO saludes ni te despidas
- Si no hay texto seleccionado, la instrucción es una pregunta/petición libre — respóndela directamente"""


def _read_clipboard() -> str:
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString
        pb = NSPasteboard.generalPasteboard()
        val = pb.stringForType_(NSPasteboardTypeString)
        return str(val) if val else ""
    except Exception:
        pass
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=1)
        return result.stdout
    except Exception:
        return ""


def _change_count() -> int | None:
    """NSPasteboard.changeCount() — se incrementa en CADA escritura al
    pasteboard, aunque el contenido sea idéntico. None si no hay PyObjC."""
    try:
        from AppKit import NSPasteboard
        return int(NSPasteboard.generalPasteboard().changeCount())
    except Exception:
        return None


def copy_selection() -> str:
    """Cmd+C then read clipboard. Detects whether a selection actually landed
    via the pasteboard's changeCount. Restores the original clipboard so the
    user's copied content is preserved.

    Returns the selected text, or "" if nothing was selected.
    """
    before = _read_clipboard()
    before_count = _change_count()
    try:
        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to keystroke "c" using command down'],
            check=True, timeout=1,
        )
    except Exception:
        return ""
    time.sleep(0.08)
    after = _read_clipboard()
    after_count = _change_count()

    # changeCount es la única señal fiable de que Cmd+C escribió algo. Comparar
    # el CONTENIDO fallaba en silencio en un caso muy común: copiar un texto,
    # seleccionar ese mismo texto y hablarle — after == before, y Command Mode
    # se creía sin selección. Fallback por contenido si PyObjC no está.
    if before_count is not None and after_count is not None:
        copied = after_count != before_count
    else:
        copied = bool(after) and after != before
    selected = after if (copied and after) else ""

    # Restore user's previous clipboard (runs after we return so the caller
    # gets the selection text first; we're on a worker thread anyway).
    if copied and before != after:
        def _restore():
            time.sleep(0.05)
            try:
                from AppKit import NSPasteboard, NSPasteboardTypeString
                pb = NSPasteboard.generalPasteboard()
                pb.clearContents()
                pb.setString_forType_(before, NSPasteboardTypeString)
            except Exception:
                pass
        import threading
        threading.Thread(target=_restore, daemon=True).start()

    return selected


class CommandModeHandler:
    def __init__(self):
        self._client = None

    def _get_client(self) -> Groq:
        if self._client is None:
            # Keychain-first (matches transcriber_groq/transform/llm_cleanup);
            # falls back to env. Using os.getenv alone broke Command Mode for
            # users whose key lives only in the Keychain.
            from core.secrets import get_key
            key = get_key("GROQ_API_KEY")
            if not key:
                raise ValueError("GROQ_API_KEY not configured")
            self._client = Groq(api_key=key, timeout=12.0)
        return self._client

    def transform(self, voice_command: str, selected_text: str) -> str:
        voice_command = (voice_command or "").strip()
        if not voice_command:
            return selected_text

        if selected_text:
            user_msg = f"TEXTO SELECCIONADO:\n{selected_text}\n\nINSTRUCCIÓN:\n{voice_command}"
        else:
            user_msg = voice_command

        try:
            completion = self._get_client().chat.completions.create(
                model=LLM_CLEANUP_MODEL,
                messages=[
                    {"role": "system", "content": _COMMAND_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.4,
                # Escala con la instruccion+seleccion para no truncar respuestas
                # largas; nunca por debajo del minimo historico.
                max_tokens=max_tokens_for(user_msg, floor=2000),
            )
            result = (completion.choices[0].message.content or "").strip()
            if result.startswith("```") and result.endswith("```"):
                result = result.strip("`").strip()
            return result or selected_text
        except Exception as e:
            log(f"command mode: LLM transform failed ({e})", level="ERROR")
            return selected_text
