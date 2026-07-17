"""Onboarding decisions — which steps to show, and whether a key is needed.

Pure logic, deliberately free of Qt and macOS so it can be tested headless.
``store_api_key`` is the one exception: it writes.

The wizard exists because SFlow needs three TCC grants that each fail silently
(see core/permissions.py) and because the app used to refuse to start without a
Groq key it does not need — the default engine runs on-device.
"""
from __future__ import annotations

import os

from core import permissions

# Bump when the wizard gains a step users must see again. `onboarding_seen_version`
# below this triggers the full flow.
ONBOARDING_VERSION = 1

STEP_WELCOME = "welcome"
STEP_MIC = "mic"
STEP_ACCESSIBILITY = "accessibility"
STEP_INPUT_MONITORING = "input_monitoring"
STEP_API_KEY = "api_key"


def api_key_required(model_local: bool, cleanup_level: str) -> bool:
    """Does this configuration actually need a Groq key?

    Only cloud transcription and LLM cleanup call Groq. The default engine
    (whisper-turbo-local) is on-device with cleanup off, so the honest answer for
    a default install is False — which is what makes "Continuar sin conexión"
    possible.
    """
    return (not model_local) or cleanup_level != "none"


def validate_api_key(raw: str) -> tuple[bool, str]:
    """Check a pasted Groq key's shape. Returns (ok, error message)."""
    key = (raw or "").strip()
    if not key:
        return False, "Pega tu API key o continúa sin conexión."
    if not key.startswith("gsk_"):
        return False, "Las keys de Groq empiezan con 'gsk_'. Revisa que copiaste la correcta."
    if len(key) < 20:
        return False, "Esa key parece incompleta. Cópiala de nuevo completa."
    return True, ""


def plan_steps(perms: dict, key_required: bool, key_present: bool) -> list[str]:
    """The steps to walk, given what's already granted.

    A permission reading ``None`` (probe unavailable) keeps its step: unknown is
    never treated as granted, because the cost of asking twice is a mild
    annoyance while the cost of skipping is a hotkey that never fires.
    """
    steps = [STEP_WELCOME, STEP_MIC]  # mic always — it doubles as the "it works" moment
    if perms.get(permissions.PERM_ACCESSIBILITY) is not True:
        steps.append(STEP_ACCESSIBILITY)
    if perms.get(permissions.PERM_INPUT_MONITORING) is not True:
        steps.append(STEP_INPUT_MONITORING)
    if key_required and not key_present:
        steps.append(STEP_API_KEY)
    return steps


def needs_onboarding(seen_version: int, perms: dict) -> bool:
    """Show the wizard? Either the user has never completed it, or a permission
    has since been revoked.

    The revocation case is the ad-hoc rebuild one: macOS drops Accessibility when
    the binary hash changes, and the user's next dictation would silently paste
    nothing. plan_steps() narrows that to just the broken step, so the rescue
    flow and first-run flow are the same machinery.
    """
    if (seen_version or 0) < ONBOARDING_VERSION:
        return True
    return any(perms.get(p) is False for p in permissions.ALL_PERMS)


def should_prompt_again(now: float, snooze_until: float) -> bool:
    """False while a user-requested snooze is still running, so a revoked
    permission nags at most once per window instead of on every launch."""
    return now >= (snooze_until or 0)


def mic_ok(peaks: list[float], threshold: float = 0.15, hits_needed: int = 5) -> bool:
    """Did we hear real speech? Requires ``hits_needed`` *consecutive* frames
    above ``threshold`` — a single spike is a door slam or a cable pop, and
    passing the mic step on one of those would defeat its purpose.
    """
    run = 0
    for p in peaks:
        run = run + 1 if p >= threshold else 0
        if run >= hits_needed:
            return True
    return False


def store_api_key(key: str, data_dir: str) -> bool:
    """Persist the key: Keychain first, then a 0600 .env for interop.

    The .env mode matters — the default 0644 would leave the key readable by
    every other user on the machine. Returns whether the Keychain write worked;
    the .env is written either way so the app still runs if Keychain is
    unavailable.
    """
    from core.secrets import set_key

    stored = False
    try:
        stored = bool(set_key("GROQ_API_KEY", key))
    except Exception:
        stored = False

    env_path = os.path.join(data_dir, ".env")
    os.makedirs(data_dir, exist_ok=True)
    with open(env_path, "w") as f:
        f.write(f"GROQ_API_KEY={key}\n")
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass

    os.environ["GROQ_API_KEY"] = key
    return stored
