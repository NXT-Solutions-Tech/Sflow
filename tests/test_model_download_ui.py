"""Download UI: the worker's progress/cancel/failure signals (mocked HF), the
optional wizard step, and plan_steps' opt-in append. Headless (offscreen)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from core.models import ModelManager, DownloadCancelled  # noqa: E402
from core import onboarding  # noqa: E402
from ui import model_download as md  # noqa: E402
from ui import onboarding_wizard as ow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# ---------- worker ----------
def test_worker_emits_finished_with_path(qapp):
    mgr = ModelManager(snapshot_fn=lambda repo, **k: "/snapshot")
    w = md.ModelDownloadWorker("repo", mgr)
    out = []
    w.finished.connect(out.append)
    w.run()
    assert out == ["/snapshot"]


def test_worker_reports_progress(qapp):
    def _snap(repo, tqdm_class=None, **k):
        # Drive the progress hook the way huggingface_hub would.
        bar = tqdm_class(total=4)
        bar.update(2)
        return "/done"

    seen = []
    w = md.ModelDownloadWorker("repo", ModelManager(snapshot_fn=_snap))
    w.progress.connect(seen.append)
    w.run()
    assert seen and seen[-1] == pytest.approx(0.5)


def test_worker_cancel_emits_cancelled(qapp):
    def _snap(repo, tqdm_class=None, **k):
        bar = tqdm_class(total=4)
        bar.update(1)  # should_cancel already True → raises inside update
        return "/done"

    w = md.ModelDownloadWorker("repo", ModelManager(snapshot_fn=_snap))
    w.cancel()
    got = []
    w.cancelled.connect(lambda: got.append(True))
    w.run()
    assert got == [True]


def test_worker_failure_is_reported_not_raised(qapp):
    def _boom(repo, **k):
        raise RuntimeError("network down")

    w = md.ModelDownloadWorker("repo", ModelManager(snapshot_fn=_boom))
    fails = []
    w.failed.connect(fails.append)
    w.run()  # must not raise
    assert fails and "network down" in fails[0]


# ---------- wizard step ----------
def test_model_step_builds_and_is_optional(qapp):
    wiz = ow.OnboardingWizard([onboarding.STEP_MODEL])
    assert isinstance(wiz.current, ow.ModelStep)
    assert wiz.current.skip_label() == "Después"   # always skippable
    assert wiz.current.can_continue() is True


def test_plan_steps_appends_model_only_when_asked():
    perms = {onboarding.permissions.PERM_ACCESSIBILITY: True,
             onboarding.permissions.PERM_INPUT_MONITORING: True}
    without = onboarding.plan_steps(perms, key_required=False, key_present=True)
    assert onboarding.STEP_MODEL not in without

    with_dl = onboarding.plan_steps(perms, key_required=False, key_present=True,
                                    offer_model_download=True)
    assert with_dl[-1] == onboarding.STEP_MODEL
