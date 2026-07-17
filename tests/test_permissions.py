"""Permission probes must fail SAFE.

The old _ensure_accessibility() returned True when its import blew up, so a
broken framework looked exactly like a granted permission — and the paste then
failed silently. These tests pin the opposite contract: unknown is None, never
True.
"""
import pytest

from core import permissions


@pytest.mark.parametrize("perm,anchor", [
    (permissions.PERM_MIC, "Privacy_Microphone"),
    (permissions.PERM_ACCESSIBILITY, "Privacy_Accessibility"),
    (permissions.PERM_INPUT_MONITORING, "Privacy_ListenEvent"),
])
def test_privacy_pane_url_points_at_the_right_pane(perm, anchor):
    url = permissions.privacy_pane_url(perm)
    assert url.startswith("x-apple.systempreferences:com.apple.preference.security?")
    assert url.endswith(anchor)


def test_unknown_permission_falls_back_to_the_privacy_root():
    """A bad key must not crash the wizard mid-flow."""
    assert permissions.privacy_pane_url("nonsense") == (
        "x-apple.systempreferences:com.apple.preference.security"
    )


def test_accessibility_probe_returns_none_when_the_framework_raises(monkeypatch):
    def boom(*_a, **_k):
        raise ImportError("ApplicationServices missing")
    monkeypatch.setattr("builtins.__import__", boom)
    assert permissions.accessibility_granted() is None


def test_input_monitoring_probe_returns_none_when_the_framework_raises(monkeypatch):
    def boom(*_a, **_k):
        raise ImportError("Quartz missing")
    monkeypatch.setattr("builtins.__import__", boom)
    assert permissions.input_monitoring_granted() is None


def test_probes_never_report_granted_on_failure(monkeypatch):
    """The regression that matters: a broken probe must not read as True."""
    def boom(*_a, **_k):
        raise RuntimeError("TCC unavailable")
    monkeypatch.setattr("builtins.__import__", boom)
    assert permissions.accessibility_granted() is not True
    assert permissions.input_monitoring_granted() is not True


def test_snapshot_reports_all_gated_permissions(monkeypatch):
    monkeypatch.setattr(permissions, "accessibility_granted", lambda prompt=False: True)
    monkeypatch.setattr(permissions, "input_monitoring_granted", lambda: False)
    monkeypatch.setattr(permissions, "mic_granted", lambda: None)
    assert permissions.snapshot() == {
        permissions.PERM_ACCESSIBILITY: True,
        permissions.PERM_INPUT_MONITORING: False,
        permissions.PERM_MIC: None,
    }


def test_open_privacy_pane_survives_a_failing_subprocess(monkeypatch):
    def boom(*_a, **_k):
        raise OSError("open unavailable")
    monkeypatch.setattr(permissions.subprocess, "Popen", boom)
    assert permissions.open_privacy_pane(permissions.PERM_ACCESSIBILITY) is False


def test_request_input_monitoring_survives_a_missing_framework(monkeypatch):
    def boom(*_a, **_k):
        raise ImportError("Quartz missing")
    monkeypatch.setattr("builtins.__import__", boom)
    assert permissions.request_input_monitoring() is False
