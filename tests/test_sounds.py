"""Start/done sounds actually play now — the toggles existed in the Hub but
were inert (nothing was wired to them)."""
import config
import core.sounds as snd


def test_start_sound_plays_only_when_enabled(monkeypatch):
    played = []
    monkeypatch.setattr(snd, "_play", lambda p: played.append(p))

    config.set_setting("sound_on_start", False)
    snd.play_start()
    assert played == []

    config.set_setting("sound_on_start", True)
    snd.play_start()
    assert played == [snd._START_SOUND]


def test_done_sound_plays_only_when_enabled(monkeypatch):
    played = []
    monkeypatch.setattr(snd, "_play", lambda p: played.append(p))

    config.set_setting("sound_on_done", False)
    snd.play_done()
    assert played == []

    config.set_setting("sound_on_done", True)
    snd.play_done()
    assert played == [snd._DONE_SOUND]


def test_play_invokes_afplay_with_a_timeout(monkeypatch):
    seen = {}
    monkeypatch.setattr(snd.subprocess, "run", lambda cmd, **kw: seen.update(cmd=cmd, kw=kw))

    class _SyncThread:
        def __init__(self, target=None, daemon=None, **k):
            self._t = target

        def start(self):
            self._t()

    monkeypatch.setattr(snd.threading, "Thread", _SyncThread)

    snd._play("/System/Library/Sounds/Tink.aiff")

    assert seen["cmd"][0] == "afplay"
    assert seen["kw"].get("timeout")  # a stuck afplay must not linger forever
