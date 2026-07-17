"""Recorder resilience: stop() can't crash the release handler or strand a
stream, error status is noticed, and the recording cap has a duration to read."""
import numpy as np
import pytest

import config
import core.recorder as rec
from core.recorder import AudioRecorder


class FakeStream:
    def __init__(self, fail_stop=False):
        self.started = self.stopped = self.closed = False
        self._fail_stop = fail_stop

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True
        if self._fail_stop:
            raise RuntimeError("PortAudio boom")

    def close(self):
        self.closed = True


def test_stop_is_guarded_against_a_failing_stream():
    r = AudioRecorder()
    r.stream = FakeStream(fail_stop=True)
    r.is_recording = True
    r._start_time = 1.0

    dur = r.stop()  # must not raise even though stream.stop() throws

    assert isinstance(dur, float)
    assert r.stream is None        # reference cleared regardless
    assert r.stream_error is True


def test_stop_clears_the_stream_on_success():
    r = AudioRecorder()
    fs = FakeStream()
    r.stream = fs
    r._start_time = 1.0

    r.stop()

    assert fs.stopped and fs.closed
    assert r.stream is None


def test_start_closes_a_lingering_stream(monkeypatch):
    r = AudioRecorder()
    lingering = FakeStream()
    r.stream = lingering
    opened = []
    monkeypatch.setattr(rec.sd, "InputStream", lambda **k: opened.append(FakeStream()) or opened[-1])
    monkeypatch.setattr(rec, "_resolve_input_device", lambda: None)

    r.start()

    assert lingering.closed is True   # the old one was cleaned up first
    assert r.stream is opened[-1]     # a fresh stream is open
    r.stop()


def test_error_status_sets_the_flag_and_resets_on_start(monkeypatch):
    r = AudioRecorder()
    indata = np.zeros((rec.BLOCK_SIZE, 1), dtype="int16")

    r._callback(indata, rec.BLOCK_SIZE, None, "input overflow")
    assert r.stream_error is True

    monkeypatch.setattr(rec.sd, "InputStream", lambda **k: FakeStream())
    monkeypatch.setattr(rec, "_resolve_input_device", lambda: None)
    r.start()
    assert r.stream_error is False  # a fresh recording starts clean
    r.stop()


def test_elapsed_is_zero_when_idle():
    assert AudioRecorder().elapsed() == 0.0


def test_elapsed_grows_while_recording(monkeypatch):
    r = AudioRecorder()
    r.is_recording = True
    r._start_time = 100.0
    monkeypatch.setattr(rec.time, "time", lambda: 105.0)
    assert r.elapsed() == pytest.approx(5.0)


def test_recording_cap_is_configured():
    assert isinstance(config.RECORDING_CAP_SECONDS, (int, float))
    assert config.RECORDING_CAP_SECONDS > 0
