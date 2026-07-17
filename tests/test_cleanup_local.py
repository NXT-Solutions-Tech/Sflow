"""Local (offline) LLM cleanup provider — mlx-lm mocked, fail-open intact."""
import sys
import types

import config
import core.llm_cleanup as lc

RAMBLE = "eh o sea queria este mandarte el reporte que quedo a medias"


def _fake_mlx_lm(output="Texto limpio."):
    fake = types.ModuleType("mlx_lm")

    class _Tok:
        def apply_chat_template(self, messages, add_generation_prompt=True):
            return "PROMPT"

    fake.load = lambda path: ("MODEL", _Tok())
    fake.generate = lambda model, tok, prompt="", max_tokens=0, verbose=False: output
    return fake


def test_local_provider_success(monkeypatch):
    config.set_setting("llm_cleanup_provider", "local")
    monkeypatch.setitem(sys.modules, "mlx_lm", _fake_mlx_lm())
    c = lc.LLMCleanup()
    monkeypatch.setattr(c._manager, "resolve_path", lambda repo: "/fake/qwen")
    assert c.clean(RAMBLE) == "Texto limpio."


def test_local_lazy_loads_once(monkeypatch):
    config.set_setting("llm_cleanup_provider", "local")
    loads = {"n": 0}
    fake = _fake_mlx_lm()
    orig_load = fake.load
    fake.load = lambda path: loads.__setitem__("n", loads["n"] + 1) or orig_load(path)
    monkeypatch.setitem(sys.modules, "mlx_lm", fake)
    c = lc.LLMCleanup()
    monkeypatch.setattr(c._manager, "resolve_path", lambda repo: "/fake/qwen")
    c.clean(RAMBLE)
    c.clean(RAMBLE)
    assert loads["n"] == 1  # resident after the first load, guarded by the lock


def test_local_fail_open_when_model_not_downloaded(monkeypatch):
    config.set_setting("llm_cleanup_provider", "local")
    monkeypatch.setitem(sys.modules, "mlx_lm", _fake_mlx_lm())
    c = lc.LLMCleanup()
    monkeypatch.setattr(c._manager, "resolve_path", lambda repo: None)  # not downloaded
    assert c.clean(RAMBLE) == RAMBLE  # raw text pasted, never blocks


def test_local_fail_open_when_mlx_lm_absent(monkeypatch):
    config.set_setting("llm_cleanup_provider", "local")
    monkeypatch.setitem(sys.modules, "mlx_lm", None)  # import fails
    c = lc.LLMCleanup()
    monkeypatch.setattr(c._manager, "resolve_path", lambda repo: "/fake/qwen")
    assert c.clean(RAMBLE) == RAMBLE
