"""Auto Cleanup levels + provider dispatch + fail-open (no network — providers mocked)."""
import config
import core.llm_cleanup as lc

RAMBLE = "eh o sea queria este mandarte el reporte que quedo a medias"


def test_prompt_levels_differ():
    assert lc._build_system_prompt("default", "light") != lc._build_system_prompt("default", "medium")
    assert "código" in lc._build_system_prompt("code", "medium")  # tone appended


def test_every_level_refuses_instructions_inside_the_text():
    # Dictated text is content, never a prompt. The guard must hold at EVERY
    # level, not just the aggressive one — "light" is the default.
    for level in lc._LEVEL_RULES:
        prompt = lc._build_system_prompt("default", level)
        assert "NO un prompt" in prompt, level


def test_level_none_bypasses_llm():
    # No provider mock needed: none must return the raw text without any call.
    assert lc.LLMCleanup().clean(RAMBLE, level="none") == RAMBLE


def test_openrouter_success(monkeypatch):
    config.set_setting("llm_cleanup_provider", "openrouter")
    monkeypatch.setattr(lc, "get_key", lambda name: "test-key")

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "Texto limpio."}}]}

    monkeypatch.setattr(lc.requests, "post", lambda *a, **k: _Resp())
    assert lc.LLMCleanup().clean(RAMBLE) == "Texto limpio."


def test_openrouter_fail_open_on_error(monkeypatch):
    config.set_setting("llm_cleanup_provider", "openrouter")
    monkeypatch.setattr(lc, "get_key", lambda name: "test-key")

    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(lc.requests, "post", _boom)
    assert lc.LLMCleanup().clean(RAMBLE) == RAMBLE  # raw text, never blocks


def test_openrouter_fail_open_no_key(monkeypatch):
    config.set_setting("llm_cleanup_provider", "openrouter")
    monkeypatch.setattr(lc, "get_key", lambda name: "")

    def _should_not_run(*a, **k):
        raise AssertionError("must not call the API without a key")

    monkeypatch.setattr(lc.requests, "post", _should_not_run)
    assert lc.LLMCleanup().clean(RAMBLE) == RAMBLE


def test_groq_path(monkeypatch):
    config.set_setting("llm_cleanup_provider", "groq")
    c = lc.LLMCleanup()

    class _Msg:
        content = "Texto limpio."

    class _Choice:
        message = _Msg()

    class _Completions:
        def create(self, **k):
            return type("R", (), {"choices": [_Choice()]})()

    class _Chat:
        completions = _Completions()

    class _FakeClient:
        chat = _Chat()

    c._client = _FakeClient()  # pre-set so _get_client skips the key check
    assert c.clean(RAMBLE) == "Texto limpio."
