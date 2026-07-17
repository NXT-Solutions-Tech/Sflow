"""The app must start without an API key, and must not nag.

main.py used to read os.getenv("GROQ_API_KEY") and sys.exit(0) if the first-run
dialog was dismissed — so the default install (an on-device engine that needs no
key) refused to launch until you pasted a cloud credential. Reading os.getenv
also ignored the Keychain, which is where the app itself stores the key.

These drive _run_onboarding_if_needed with the wizard stubbed out.
"""
import pytest

import main
from core import onboarding


class FakeWizard:
    """Records construction instead of showing anything."""
    last = None

    def __init__(self, steps, key_required=False):
        self.steps = steps
        self.key_required = key_required
        FakeWizard.last = self
        self.shown = False

    def exec(self):
        self.shown = True
        return 1


@pytest.fixture
def wizard(monkeypatch):
    FakeWizard.last = None
    import ui.onboarding_wizard as ow
    monkeypatch.setattr(ow, "OnboardingWizard", FakeWizard)
    return FakeWizard


@pytest.fixture
def settings(monkeypatch):
    """In-memory settings; set_setting writes are captured, not persisted."""
    store = {}
    monkeypatch.setattr(main, "get_setting", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(main, "set_setting", lambda k, v: store.__setitem__(k, v))
    return store


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.setattr(main, "get_key", lambda _n: "")
    monkeypatch.setattr(main.permissions, "snapshot", lambda: {
        main.permissions.PERM_ACCESSIBILITY: True,
        main.permissions.PERM_INPUT_MONITORING: True,
    })
    monkeypatch.setattr(main, "get_stt_model", lambda: {"local": True, "id": "whisper-turbo-local"})


# ---------- the key is optional ----------
def test_default_offline_install_is_never_asked_for_a_key(wizard, settings, monkeypatch):
    """The headline regression: local engine + cleanup off -> no key step."""
    monkeypatch.setattr(main, "get_setting",
                        lambda k, d=None: "none" if k == "auto_cleanup_level" else settings.get(k, d))

    main._run_onboarding_if_needed()

    assert onboarding.STEP_API_KEY not in wizard.last.steps
    assert wizard.last.key_required is False


def test_a_cloud_model_does_ask_for_a_key(wizard, settings, monkeypatch):
    monkeypatch.setattr(main, "get_stt_model", lambda: {"local": False, "id": "groq-turbo"})

    main._run_onboarding_if_needed()

    assert onboarding.STEP_API_KEY in wizard.last.steps
    assert wizard.last.key_required is True


def test_auto_cleanup_makes_the_key_required_even_on_a_local_model(wizard, settings, monkeypatch):
    """Cleanup calls Groq regardless of which engine transcribed."""
    monkeypatch.setattr(main, "get_setting",
                        lambda k, d=None: "light" if k == "auto_cleanup_level" else settings.get(k, d))

    main._run_onboarding_if_needed()

    assert wizard.last.key_required is True


def test_a_key_in_the_keychain_skips_the_key_step(wizard, settings, monkeypatch):
    """os.getenv alone missed Keychain-only users — where the app puts the key."""
    monkeypatch.setattr(main, "get_key", lambda _n: "gsk_" + "a" * 40)
    monkeypatch.setattr(main, "get_stt_model", lambda: {"local": False, "id": "groq-turbo"})

    main._run_onboarding_if_needed()

    assert onboarding.STEP_API_KEY not in wizard.last.steps


# ---------- when the wizard runs ----------
def test_first_run_shows_the_wizard(wizard, settings):
    main._run_onboarding_if_needed()
    assert wizard.last is not None and wizard.last.shown


def test_a_completed_healthy_install_is_left_alone(wizard, settings):
    settings["onboarding_seen_version"] = onboarding.ONBOARDING_VERSION

    main._run_onboarding_if_needed()

    assert wizard.last is None


def test_a_revoked_permission_reopens_the_wizard(wizard, settings, monkeypatch):
    """The ad-hoc rebuild case that _ensure_accessibility used to cover."""
    settings["onboarding_seen_version"] = onboarding.ONBOARDING_VERSION
    monkeypatch.setattr(main.permissions, "snapshot", lambda: {
        main.permissions.PERM_ACCESSIBILITY: False,
        main.permissions.PERM_INPUT_MONITORING: True,
    })

    main._run_onboarding_if_needed()

    assert wizard.last.steps == [onboarding.STEP_WELCOME, onboarding.STEP_MIC,
                                 onboarding.STEP_ACCESSIBILITY]


def test_a_snooze_suppresses_the_reprompt(wizard, settings, monkeypatch):
    settings["onboarding_seen_version"] = onboarding.ONBOARDING_VERSION
    settings["onboarding_snooze_until"] = 9_999_999_999
    monkeypatch.setattr(main.permissions, "snapshot", lambda: {
        main.permissions.PERM_ACCESSIBILITY: False,
        main.permissions.PERM_INPUT_MONITORING: True,
    })

    main._run_onboarding_if_needed()

    assert wizard.last is None


def test_completing_the_wizard_records_the_version(wizard, settings):
    main._run_onboarding_if_needed()
    assert settings["onboarding_seen_version"] == onboarding.ONBOARDING_VERSION


# ---------- onboarding must never be a gate ----------
def test_a_broken_wizard_does_not_stop_the_app(settings, monkeypatch):
    """It's a helper. If it explodes, the app still starts."""
    import ui.onboarding_wizard as ow

    class Explodes:
        def __init__(self, *a, **k):
            raise RuntimeError("Qt is having a bad day")

    monkeypatch.setattr(ow, "OnboardingWizard", Explodes)

    main._run_onboarding_if_needed()  # must not raise


def test_closing_the_wizard_midway_does_not_record_it(settings, monkeypatch):
    """Reject (closed the window before finishing) must NOT mark onboarding seen,
    or a half-finished run permanently skips the rescue flow."""
    import ui.onboarding_wizard as ow

    class Rejected:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return 0  # QDialog.DialogCode.Rejected

    monkeypatch.setattr(ow, "OnboardingWizard", Rejected)

    main._run_onboarding_if_needed()

    assert "onboarding_seen_version" not in settings


def test_a_broken_wizard_does_not_mark_onboarding_as_seen(settings, monkeypatch):
    """Otherwise a one-off failure would permanently skip onboarding."""
    import ui.onboarding_wizard as ow

    class Explodes:
        def __init__(self, *a, **k):
            raise RuntimeError("boom")

    monkeypatch.setattr(ow, "OnboardingWizard", Explodes)

    main._run_onboarding_if_needed()

    assert "onboarding_seen_version" not in settings
