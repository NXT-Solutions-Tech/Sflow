"""ModelManager — the catalog of model weights and where they live on disk.

The promise SFlow makes is "offline out of the box". That only holds if the app
is honest about which weights are present: Parakeet ships inside the bundle
(F2 step 7), Whisper Turbo and the optional local cleanup model are downloaded on
demand. Nothing downloads implicitly — a transcriber asks ``is_available`` first,
and a missing model raises ``ModelNotDownloaded`` so the UI can say "download it
in Ajustes → Modelo" instead of the old, false "missing API key".

Resolution order is bundle-first: a weight bundled into the .app
(``sys._MEIPASS/models/<name>``) wins over the Hugging Face cache, so the frozen
app never re-downloads what it already ships.
"""
import os
import sys

try:
    from huggingface_hub import snapshot_download as _hf_snapshot_download
except Exception:  # huggingface_hub missing (shouldn't happen — it's a dep)
    _hf_snapshot_download = None


class ModelNotDownloaded(Exception):
    """A local model's weights aren't on disk yet. Carries the ids so the error
    can point the user at the exact download."""

    def __init__(self, repo_id: str, model_id: str = ""):
        self.repo_id = repo_id
        self.model_id = model_id or repo_id
        super().__init__(f"model weights not downloaded: {repo_id}")


class DownloadCancelled(Exception):
    """Raised out of the progress hook when the user cancels a download."""


# Catalog keyed by repo_id (what the transcribers already carry). `bundled` marks
# weights shipped inside the .app; `size_mb` drives the UI copy ("Descargar 1.6GB").
CATALOG: dict[str, dict] = {
    "mlx-community/parakeet-tdt-0.6b-v3": {"label": "Parakeet v3", "size_mb": 600, "bundled": True, "kind": "stt"},
    "mlx-community/whisper-large-v3-turbo": {"label": "Whisper Turbo", "size_mb": 1600, "bundled": False, "kind": "stt"},
    "mlx-community/Qwen2.5-1.5B-Instruct-4bit": {"label": "Cleanup local (Qwen 1.5B)", "size_mb": 900, "bundled": False, "kind": "llm"},
}


def catalog_entry(repo_id: str) -> dict:
    return CATALOG.get(repo_id, {"label": repo_id.split("/")[-1], "size_mb": 0, "bundled": False, "kind": "stt"})


def missing_code_for_selection(model: dict, manager: "ModelManager") -> str | None:
    """Settings model-picker gate.

    Returns None if the model is usable now (a cloud model, or a local one whose
    weights are present), else error_messages.CODE_MODEL_MISSING. Crucially it is
    NEVER a key error: an undownloaded local model needs a download, not a key,
    and conflating the two is exactly the false message this replaces.
    """
    if not model.get("local"):
        return None
    if manager.is_available(model.get("model", "")):
        return None
    from core import error_messages
    return error_messages.CODE_MODEL_MISSING


def bundle_dir(repo_id: str) -> str | None:
    """Where a bundled weight lands under PyInstaller's Tree, or None in dev mode.
    build.sh stages ``models/<basename>`` and the spec copies it into _MEIPASS."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return os.path.join(base, "models", repo_id.split("/")[-1])
    return None


class ModelManager:
    """Stateless facade over the bundle + Hugging Face cache. `snapshot_fn` is
    injectable so tests never hit the network or the real cache."""

    def __init__(self, snapshot_fn=None):
        self._snapshot = snapshot_fn if snapshot_fn is not None else _hf_snapshot_download

    def resolve_path(self, repo_id: str) -> str | None:
        """Bundle-first path to the weights, or None if not present anywhere.
        Never triggers a network download (``local_files_only``)."""
        bd = bundle_dir(repo_id)
        if bd and os.path.isdir(bd):
            return bd
        if self._snapshot is None:
            return None
        try:
            return self._snapshot(repo_id, local_files_only=True)
        except Exception:
            # LocalEntryNotFoundError (not cached) and anything else → "not here".
            return None

    def is_available(self, repo_id: str) -> bool:
        """True iff the weights are on disk (bundle or cache). This is the check
        that gates warm-loading and transcription — no implicit downloads."""
        return self.resolve_path(repo_id) is not None

    def download(self, repo_id: str, progress_cb=None, should_cancel=None) -> str:
        """Fetch the weights, reporting fraction-complete via ``progress_cb`` and
        aborting (raising DownloadCancelled) when ``should_cancel()`` turns True.
        Returns the local snapshot path."""
        if self._snapshot is None:
            raise RuntimeError("huggingface_hub unavailable")
        kwargs = {}
        tqdm_cls = _progress_tqdm(progress_cb, should_cancel)
        if tqdm_cls is not None:
            kwargs["tqdm_class"] = tqdm_cls
        return self._snapshot(repo_id, **kwargs)


def _progress_tqdm(progress_cb, should_cancel):
    """A tqdm subclass that forwards fraction-complete to ``progress_cb`` and
    raises DownloadCancelled from update() when asked to stop. Returns None when
    neither hook is set (let snapshot_download use its default bar)."""
    if progress_cb is None and should_cancel is None:
        return None
    try:
        from huggingface_hub.utils import tqdm as _base_tqdm
    except Exception:
        from tqdm import tqdm as _base_tqdm

    class _ProgressTqdm(_base_tqdm):
        def update(self, n=1):
            ret = super().update(n)
            if should_cancel is not None and should_cancel():
                raise DownloadCancelled()
            if progress_cb is not None:
                total = getattr(self, "total", None)
                if total:
                    progress_cb(min(1.0, (self.n or 0) / total))
            return ret

    return _ProgressTqdm
