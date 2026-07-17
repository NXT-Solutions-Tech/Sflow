"""ModelManager: availability, bundle-first resolution, download progress/cancel,
and the honest 'not downloaded' code — all with Hugging Face mocked (no network,
no real cache)."""
import io

import pytest

import core.models as m
from core.models import (
    DownloadCancelled, ModelManager, ModelNotDownloaded, missing_code_for_selection,
)
from core import error_messages


def test_is_available_true_when_cached():
    mgr = ModelManager(snapshot_fn=lambda repo, **k: "/cache/whisper")
    assert mgr.is_available("mlx-community/whisper-large-v3-turbo") is True
    assert mgr.resolve_path("mlx-community/whisper-large-v3-turbo") == "/cache/whisper"


def test_is_available_false_when_not_cached():
    def _miss(repo, **k):
        raise RuntimeError("LocalEntryNotFoundError")
    mgr = ModelManager(snapshot_fn=_miss)
    assert mgr.is_available("whatever") is False
    assert mgr.resolve_path("whatever") is None


def test_availability_uses_local_files_only():
    seen = {}
    ModelManager(snapshot_fn=lambda repo, **k: seen.update(k) or "/c").is_available("r")
    assert seen.get("local_files_only") is True


def test_resolve_path_is_bundle_first(monkeypatch, tmp_path):
    bundled = tmp_path / "whisper-large-v3-turbo"
    bundled.mkdir()
    monkeypatch.setattr(m, "bundle_dir", lambda repo: str(bundled))
    calls = {"n": 0}

    def _snap(repo, **k):
        calls["n"] += 1
        return "/cache"

    mgr = ModelManager(snapshot_fn=_snap)
    assert mgr.resolve_path("mlx-community/whisper-large-v3-turbo") == str(bundled)
    assert calls["n"] == 0  # a bundled weight never consults the HF cache


def test_download_without_hooks_omits_tqdm():
    def _snap(repo, **k):
        assert "tqdm_class" not in k
        return "/p"

    assert ModelManager(snapshot_fn=_snap).download("repo") == "/p"


def test_download_passes_a_tqdm_when_hooks_present():
    def _snap(repo, **k):
        assert k.get("tqdm_class") is not None
        return "/downloaded"

    mgr = ModelManager(snapshot_fn=_snap)
    assert mgr.download("repo", progress_cb=lambda f: None) == "/downloaded"


def test_progress_tqdm_forwards_fraction_and_cancels():
    fracs = []
    cancel = {"v": False}
    Tq = m._progress_tqdm(lambda f: fracs.append(f), lambda: cancel["v"])
    bar = Tq(total=10, file=io.StringIO())
    bar.update(5)
    assert fracs[-1] == pytest.approx(0.5)
    cancel["v"] = True
    with pytest.raises(DownloadCancelled):
        bar.update(1)


def test_model_not_downloaded_maps_to_the_honest_code():
    assert error_messages.classify_exception(ModelNotDownloaded("repo")) == error_messages.CODE_MODEL_MISSING


# ---------- missing_code_for_selection: the Settings gate ----------
def test_undownloaded_local_model_is_model_missing_not_a_key_error():
    mgr = ModelManager(snapshot_fn=lambda r, **k: (_ for _ in ()).throw(RuntimeError()))
    code = missing_code_for_selection({"local": True, "model": "mlx-community/whisper-large-v3-turbo"}, mgr)
    assert code == error_messages.CODE_MODEL_MISSING
    assert code != error_messages.CODE_NO_KEY  # the whole point: not a key problem


def test_cloud_model_never_needs_a_download():
    mgr = ModelManager(snapshot_fn=lambda r, **k: None)
    assert missing_code_for_selection({"local": False, "model": "x"}, mgr) is None


def test_downloaded_local_model_is_ready():
    mgr = ModelManager(snapshot_fn=lambda r, **k: "/cache")
    assert missing_code_for_selection({"local": True, "model": "x"}, mgr) is None
