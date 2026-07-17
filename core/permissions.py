"""macOS permission probes — Accessibility, Input Monitoring, Microphone.

SFlow needs three separate TCC grants and fails differently without each one:

- **Accessibility** — CGEventPost silently drops the synthesized keystrokes, so
  dictation transcribes fine and the text never lands. Revoked on every ad-hoc
  rebuild (the signature hash changes; see CLAUDE.md).
- **Input Monitoring** — pynput's listener never fires. It does not raise and
  ``listener.running`` still reads True, so the app looks healthy while being
  completely deaf to the hotkey.
- **Microphone** — the recorder raises on stream open.

Every probe returns ``None`` when it cannot answer (framework import failed, or
the API raised) — never a hopeful ``True``. Callers must treat ``None`` as
"unknown, show the step anyway": pretending a permission exists is exactly how a
missing grant becomes a silent failure.
"""
from __future__ import annotations

import subprocess

PERM_MIC = "mic"
PERM_ACCESSIBILITY = "accessibility"
PERM_INPUT_MONITORING = "input_monitoring"

ALL_PERMS = (PERM_MIC, PERM_ACCESSIBILITY, PERM_INPUT_MONITORING)

# System Settings → Privacy & Security panes, keyed by permission.
_PANES = {
    PERM_MIC: "Privacy_Microphone",
    PERM_ACCESSIBILITY: "Privacy_Accessibility",
    PERM_INPUT_MONITORING: "Privacy_ListenEvent",
}


def privacy_pane_url(perm: str) -> str:
    """Deep link to the Privacy pane for ``perm``. Falls back to the Privacy
    root for an unknown permission rather than raising — a wrong pane is a far
    better outcome than a crashed wizard."""
    anchor = _PANES.get(perm)
    base = "x-apple.systempreferences:com.apple.preference.security"
    return f"{base}?{anchor}" if anchor else base


def open_privacy_pane(perm: str) -> bool:
    """Open System Settings at the pane for ``perm``. Returns success."""
    try:
        subprocess.Popen(["open", privacy_pane_url(perm)])
        return True
    except Exception:
        return False


def accessibility_granted(prompt: bool = False) -> bool | None:
    """Is SFlow trusted for Accessibility? ``prompt=True`` lets macOS show its
    own "grant this app" dialog (only meaningful the first time)."""
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions
        return bool(AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": bool(prompt)}))
    except Exception:
        return None


def input_monitoring_granted() -> bool | None:
    """Can we tap key events (what pynput needs)? This is the permission the app
    never used to ask for."""
    try:
        from Quartz import CGPreflightListenEventAccess
        return bool(CGPreflightListenEventAccess())
    except Exception:
        return None


def request_input_monitoring() -> bool:
    """Ask macOS for Input Monitoring. This is the only call that raises the
    system's own grant dialog; the preflight above never does. Returns whether
    the request was issued, not whether it was granted."""
    try:
        from Quartz import CGRequestListenEventAccess
        CGRequestListenEventAccess()
        return True
    except Exception:
        return False


def snapshot() -> dict[str, bool | None]:
    """Current state of every permission. Never prompts — safe to call at
    startup to decide whether onboarding is needed.

    The mic is deliberately absent: there is no preflight for it that doesn't
    either prompt or pull in AVFoundation, and the wizard tests it for real by
    opening a stream instead.
    """
    return {
        PERM_ACCESSIBILITY: accessibility_granted(prompt=False),
        PERM_INPUT_MONITORING: input_monitoring_granted(),
    }
