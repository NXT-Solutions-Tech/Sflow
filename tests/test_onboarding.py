"""Onboarding decisions: which steps to show, and when a key is truly needed."""
import os

import pytest

from core import onboarding, permissions
from core.onboarding import (
    STEP_ACCESSIBILITY, STEP_API_KEY, STEP_INPUT_MONITORING, STEP_MIC, STEP_WELCOME,
)


# ---------- api_key_required ----------
@pytest.mark.parametrize("local,cleanup,expected", [
    # The headline case: default install is local + cleanup off -> no key needed.
    (True, "none", False),
    (True, "light", True),      # cleanup calls Groq
    (True, "medium", True),
    (False, "none", True),      # cloud engine calls Groq
    (False, "light", True),
])
def test_api_key_required(local, cleanup, expected):
    assert onboarding.api_key_required(local, cleanup) is expected


def test_default_offline_install_needs_no_key():
    """Guards the whole point of the change: the app must start keyless."""
    assert onboarding.api_key_required(model_local=True, cleanup_level="none") is False


# ---------- validate_api_key ----------
@pytest.mark.parametrize("raw", ["", "   ", None])
def test_validate_rejects_empty(raw):
    ok, err = onboarding.validate_api_key(raw)
    assert ok is False and err


def test_validate_rejects_wrong_prefix():
    ok, err = onboarding.validate_api_key("sk-openai-style-key-that-is-long")
    assert ok is False and "gsk_" in err


def test_validate_rejects_too_short():
    ok, err = onboarding.validate_api_key("gsk_short")
    assert ok is False and err


def test_validate_accepts_a_well_formed_key():
    ok, err = onboarding.validate_api_key("gsk_" + "a" * 40)
    assert ok is True and err == ""


def test_validate_tolerates_surrounding_whitespace():
    """Pasting from a browser routinely drags in a newline."""
    ok, _ = onboarding.validate_api_key("  gsk_" + "a" * 40 + "\n")
    assert ok is True


# ---------- plan_steps ----------
def _perms(access=True, input_mon=True):
    return {
        permissions.PERM_ACCESSIBILITY: access,
        permissions.PERM_INPUT_MONITORING: input_mon,
    }


def test_everything_granted_and_no_key_needed_is_just_welcome_and_mic():
    steps = onboarding.plan_steps(_perms(), key_required=False, key_present=False)
    assert steps == [STEP_WELCOME, STEP_MIC]


def test_nothing_granted_walks_every_step():
    steps = onboarding.plan_steps(
        _perms(access=False, input_mon=False), key_required=True, key_present=False
    )
    assert steps == [STEP_WELCOME, STEP_MIC, STEP_ACCESSIBILITY,
                     STEP_INPUT_MONITORING, STEP_API_KEY]


@pytest.mark.parametrize("unknown", [None])
def test_unknown_permission_still_shows_its_step(unknown):
    """None means "we couldn't ask" — it must never be read as granted."""
    steps = onboarding.plan_steps(
        _perms(access=unknown, input_mon=unknown), key_required=False, key_present=False
    )
    assert STEP_ACCESSIBILITY in steps and STEP_INPUT_MONITORING in steps


def test_present_key_skips_the_key_step():
    steps = onboarding.plan_steps(_perms(), key_required=True, key_present=True)
    assert STEP_API_KEY not in steps


def test_key_step_appears_only_when_required_and_absent():
    steps = onboarding.plan_steps(_perms(), key_required=True, key_present=False)
    assert steps[-1] == STEP_API_KEY


def test_only_the_revoked_permission_gets_a_step():
    """The rescue flow after a rebuild: one broken grant, one step."""
    steps = onboarding.plan_steps(
        _perms(access=False, input_mon=True), key_required=False, key_present=False
    )
    assert steps == [STEP_WELCOME, STEP_MIC, STEP_ACCESSIBILITY]


# ---------- needs_onboarding ----------
def test_first_run_needs_onboarding():
    assert onboarding.needs_onboarding(0, _perms()) is True


def test_completed_and_healthy_does_not_reprompt():
    assert onboarding.needs_onboarding(onboarding.ONBOARDING_VERSION, _perms()) is False


def test_revoked_permission_reopens_the_wizard():
    """The ad-hoc rebuild case — macOS silently drops Accessibility."""
    assert onboarding.needs_onboarding(
        onboarding.ONBOARDING_VERSION, _perms(access=False)
    ) is True


def test_unknown_permission_does_not_reopen_the_wizard_after_completion():
    """None is "couldn't ask", not "revoked" — nagging a finished user on every
    launch because a probe is unavailable would be worse than staying quiet."""
    assert onboarding.needs_onboarding(
        onboarding.ONBOARDING_VERSION, _perms(access=None)
    ) is False


def test_a_newer_wizard_version_reprompts():
    assert onboarding.needs_onboarding(onboarding.ONBOARDING_VERSION - 1, _perms()) is True


# ---------- should_prompt_again ----------
def test_snooze_suppresses_the_prompt():
    assert onboarding.should_prompt_again(now=100.0, snooze_until=500.0) is False


def test_prompt_returns_after_the_snooze_expires():
    assert onboarding.should_prompt_again(now=600.0, snooze_until=500.0) is True


def test_no_snooze_set_always_prompts():
    assert onboarding.should_prompt_again(now=1.0, snooze_until=0) is True


# ---------- mic_ok ----------
def test_silence_never_passes():
    assert onboarding.mic_ok([0.0] * 50) is False


def test_sustained_speech_passes():
    assert onboarding.mic_ok([0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.2]) is True


def test_a_single_spike_is_not_speech():
    """A door slam must not pass the mic test."""
    assert onboarding.mic_ok([0.0, 0.9, 0.0, 0.0, 0.8, 0.0, 0.9, 0.0]) is False


def test_the_run_must_be_consecutive():
    assert onboarding.mic_ok([0.9, 0.9, 0.0, 0.9, 0.9, 0.0, 0.9, 0.9]) is False


def test_empty_peaks_is_not_a_pass():
    assert onboarding.mic_ok([]) is False


# ---------- store_api_key ----------
def test_store_api_key_writes_keychain_and_a_private_env(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("core.secrets.set_key", lambda n, v: calls.append((n, v)) or True)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    key = "gsk_" + "a" * 40

    assert onboarding.store_api_key(key, str(tmp_path)) is True

    assert calls == [("GROQ_API_KEY", key)]
    env = tmp_path / ".env"
    assert env.read_text() == f"GROQ_API_KEY={key}\n"
    # 0600: the default 0644 would expose the key to every user on the machine.
    assert oct(env.stat().st_mode & 0o777) == "0o600"
    assert os.environ["GROQ_API_KEY"] == key


def test_env_is_still_written_when_the_keychain_fails(tmp_path, monkeypatch):
    """Keychain unavailable must not cost the user their key."""
    def boom(*_a):
        raise RuntimeError("no keyring backend")
    monkeypatch.setattr("core.secrets.set_key", boom)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    key = "gsk_" + "b" * 40

    assert onboarding.store_api_key(key, str(tmp_path)) is False
    assert (tmp_path / ".env").read_text() == f"GROQ_API_KEY={key}\n"
