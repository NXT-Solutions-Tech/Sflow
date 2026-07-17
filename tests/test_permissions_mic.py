"""Mic is now part of permissions.snapshot() via AVCaptureDevice's read-only
status (never prompts)."""
import sys
import types

from core import permissions


def _fake_av(status):
    fake = types.ModuleType("AVFoundation")

    class _Dev:
        @staticmethod
        def authorizationStatusForMediaType_(_m):
            return status

    fake.AVCaptureDevice = _Dev
    fake.AVMediaTypeAudio = "audio"
    return fake


def test_snapshot_includes_the_mic():
    assert permissions.PERM_MIC in permissions.snapshot()


def test_mic_status_maps_authorized_denied_undetermined(monkeypatch):
    monkeypatch.setitem(sys.modules, "AVFoundation", _fake_av(3))
    assert permissions.mic_granted() is True          # authorized
    monkeypatch.setitem(sys.modules, "AVFoundation", _fake_av(2))
    assert permissions.mic_granted() is False         # denied
    monkeypatch.setitem(sys.modules, "AVFoundation", _fake_av(0))
    assert permissions.mic_granted() is None          # not determined → unknown


def test_mic_none_when_framework_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "AVFoundation", None)  # import fails
    assert permissions.mic_granted() is None
