"""Wizard behaviour that users depend on.

The rest of tests/ is pure logic with no Qt, but the offline escape hatch and the
"always accept" contract live in the widget layer and are exactly the kind of
thing that regresses silently. These run offscreen, and the wizard's side effects
are gated behind showEvent, so constructing steps here touches no mic and no TCC.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from core.onboarding import (  # noqa: E402
    STEP_ACCESSIBILITY, STEP_API_KEY, STEP_INPUT_MONITORING, STEP_MIC, STEP_WELCOME,
)
from ui import onboarding_wizard as ow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_side_effects(monkeypatch):
    """Belt and braces: a constructed step must never prompt or open Settings."""
    monkeypatch.setattr(ow.permissions, "accessibility_granted", lambda prompt=False: False)
    monkeypatch.setattr(ow.permissions, "input_monitoring_granted", lambda: False)
    monkeypatch.setattr(ow.permissions, "request_input_monitoring", lambda: False)
    monkeypatch.setattr(ow.permissions, "open_privacy_pane", lambda perm: False)


# ---------- step construction ----------
@pytest.mark.parametrize("sid,klass", [
    (STEP_WELCOME, ow.WelcomeStep),
    (STEP_MIC, ow.MicStep),
    (STEP_ACCESSIBILITY, ow.AccessibilityStep),
    (STEP_INPUT_MONITORING, ow.InputMonitoringStep),
    (STEP_API_KEY, ow.ApiKeyStep),
])
def test_each_step_id_builds_its_widget(qapp, sid, klass):
    wiz = ow.OnboardingWizard([sid])
    assert isinstance(wiz.current, klass)
    assert wiz.current.step_id == sid


def test_the_full_flow_keeps_the_planned_order(qapp):
    steps = [STEP_WELCOME, STEP_MIC, STEP_ACCESSIBILITY, STEP_INPUT_MONITORING, STEP_API_KEY]
    wiz = ow.OnboardingWizard(steps)
    assert [s.step_id for s in wiz._steps] == steps


def test_an_unknown_step_id_degrades_to_welcome(qapp):
    """A bad id must not crash first run."""
    assert isinstance(ow.OnboardingWizard(["nonsense"]).current, ow.WelcomeStep)


# ---------- the offline escape hatch (requirement 2) ----------
def test_optional_key_offers_the_offline_path(qapp):
    step = ow.ApiKeyStep(key_required=False)
    assert step.skip_label() == "Continuar sin conexión"


def test_required_key_has_no_offline_path(qapp):
    step = ow.ApiKeyStep(key_required=True)
    assert step.skip_label() is None


def test_empty_key_continues_when_optional(qapp):
    """The point of the whole change: a local user walks past this untouched."""
    step = ow.ApiKeyStep(key_required=False)
    assert step.can_continue() is True


def test_empty_key_blocks_when_required(qapp):
    step = ow.ApiKeyStep(key_required=True)
    assert step.can_continue() is False
    assert step.status.text()


def test_a_typed_key_is_validated_even_when_optional(qapp):
    """Optional means "you may skip", not "we'll accept garbage"."""
    step = ow.ApiKeyStep(key_required=False)
    step.key_input.setText("not-a-groq-key")
    assert step.can_continue() is False
    assert "gsk_" in step.status.text()


def test_a_valid_key_is_stored(qapp, monkeypatch, tmp_path):
    saved = {}
    monkeypatch.setattr(ow.onboarding, "store_api_key",
                        lambda k, d: saved.update(key=k, dir=d) or True)
    step = ow.ApiKeyStep(key_required=True)
    key = "gsk_" + "a" * 40
    step.key_input.setText(key)

    assert step.can_continue() is True
    assert saved["key"] == key


def test_required_key_copy_does_not_claim_to_be_optional(qapp):
    """Calling it optional while refusing to continue without it would be a lie."""
    required = ow.ApiKeyStep(key_required=True)
    titles = [lb.text() for lb in required.findChildren(ow.QLabel)]
    assert not any("opcional" in t.lower() for t in titles)


# ---------- permission steps ----------
def test_a_granted_permission_reports_granted(qapp, monkeypatch):
    monkeypatch.setattr(ow.permissions, "accessibility_granted", lambda prompt=False: True)
    step = ow.AccessibilityStep()
    step._poll()
    assert "✓" in step.status.text()
    assert step.skip_label() is None  # nothing left to skip


def test_a_denied_permission_stays_skippable(qapp):
    step = ow.AccessibilityStep()
    step._poll()
    assert step.skip_label() == "Ahora no"


def test_an_unverifiable_permission_does_not_claim_granted(qapp, monkeypatch):
    """None means "couldn't ask" — the UI must not imply success."""
    monkeypatch.setattr(ow.permissions, "accessibility_granted", lambda prompt=False: None)
    step = ow.AccessibilityStep()
    step._poll()
    assert "✓" not in step.status.text()


def test_input_monitoring_step_requests_the_permission_once(qapp, monkeypatch):
    """CGPreflight never prompts; only CGRequest does. It must actually fire."""
    calls = []
    monkeypatch.setattr(ow.permissions, "request_input_monitoring",
                        lambda: calls.append(1) or True)
    step = ow.InputMonitoringStep()
    step.request()
    step.request()
    assert len(calls) == 1


def test_accessibility_prompts_only_once(qapp, monkeypatch):
    prompts = []
    monkeypatch.setattr(ow.permissions, "accessibility_granted",
                        lambda prompt=False: prompts.append(prompt) or False)
    step = ow.AccessibilityStep()
    step.request()
    step.request()
    assert prompts.count(True) == 1


# ---------- mic step ----------
def test_mic_step_reports_a_blocked_microphone(qapp, monkeypatch):
    """A denied mic raises on stream open; the user must be told, not left
    staring at motionless bars."""
    class Boom:
        def start(self):
            raise RuntimeError("PortAudio: device unavailable")

    monkeypatch.setattr("core.recorder.AudioRecorder", lambda: Boom())
    step = ow.MicStep()
    step.on_enter()
    assert "bloque" in step.status.text().lower()


def test_mic_step_releases_the_stream_on_leave(qapp, monkeypatch):
    """Two live PortAudio streams can hang a device, and SFlowApp opens its own
    the moment the wizard closes."""
    stopped = []

    class Fake:
        audio_queue = None

        def start(self):
            pass

        def stop(self):
            stopped.append(1)
            return 0.0

    monkeypatch.setattr("core.recorder.AudioRecorder", lambda: Fake())
    step = ow.MicStep()
    step.on_enter()
    step.on_leave()
    assert stopped == [1]


# ---------- the always-accept contract ----------
def test_walking_off_the_last_step_accepts(qapp):
    """The wizard may inform, but it must never stop the app from starting."""
    wiz = ow.OnboardingWizard([STEP_WELCOME])
    wiz._advance()
    assert wiz.result() == ow.QDialog.DialogCode.Accepted
