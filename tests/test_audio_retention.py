"""Retention of retry-WAVs must be true in the failure cases too.

The WAV is written at hotkey-release, *before* we know a row will exist. Every
dictation that dies after that write (silence, transcribe raising, db.insert
failing) used to leak the file forever, because prune_old_audio_paths only ever
walked audio_path columns — an unreferenced WAV was invisible to it. These guard
both halves of the fix: the write only survives an insert, and the mtime sweep
collects whatever still slips through.
"""
import os
import time
import types

import main
from db.database import TranscriptionDB


def _wav(path) -> str:
    path.write_bytes(b"RIFF....WAVEfake")
    return str(path)


def _age(path: str, days: float):
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def _app(db=None, **kw):
    """Minimal stand-in for SFlowApp: the audio-retention paths only touch these."""
    fake = types.SimpleNamespace(
        transcriber=types.SimpleNamespace(transcribe=lambda buf: ("hola", "m1")),
        transcription_done=types.SimpleNamespace(emit=lambda *a: None),
        transcription_error=types.SimpleNamespace(emit=lambda *a: None),
        db=db,
        pill=types.SimpleNamespace(set_state=lambda *a: None),
        notify=lambda *a: None,
        _pending_audio_path=None,
        _dictation_app=None,
    )
    fake.__dict__.update(kw)
    return fake


class _DB:
    def __init__(self, fail=False):
        self.rows = []
        self.fail = fail

    def insert(self, **kw):
        if self.fail:
            raise RuntimeError("disk full")
        self.rows.append(kw)
        return 1


# ---- (a) the happy path must KEEP the WAV (Hub re-transcribe depends on it) ----

def test_successful_dictation_keeps_its_wav(tmp_path, monkeypatch):
    wav = _wav(tmp_path / "ok.wav")
    monkeypatch.setattr(main, "paste_text", lambda t: True)
    db = _DB()
    emitted = []
    app = _app(db, transcription_done=types.SimpleNamespace(emit=lambda *a: emitted.append(a)))

    main.SFlowApp._transcribe_worker(app, b"", 1.0, wav)
    # The path rides the signal — an attribute would cross wires between two
    # in-flight dictations.
    assert emitted == [("hola", 1.0, "m1", wav)]
    main.SFlowApp._on_transcription_done(app, *emitted[0])

    assert os.path.exists(wav), "a live row's WAV must survive"
    assert db.rows[0]["audio_path"] == wav


# ---- (b) every failure path must leave NO orphan ----

def test_silent_dictation_leaves_no_orphan(tmp_path):
    wav = _wav(tmp_path / "silent.wav")
    app = _app(transcriber=types.SimpleNamespace(transcribe=lambda buf: ("", "m1")))

    main.SFlowApp._transcribe_worker(app, b"", 1.0, wav)

    assert not os.path.exists(wav)


def test_transcribe_exception_leaves_no_orphan(tmp_path):
    wav = _wav(tmp_path / "boom.wav")

    def _boom(buf):
        raise RuntimeError("engine died")

    app = _app(transcriber=types.SimpleNamespace(transcribe=_boom))

    main.SFlowApp._transcribe_worker(app, b"", 1.0, wav)

    assert not os.path.exists(wav)


def test_failed_insert_leaves_no_orphan(tmp_path, monkeypatch):
    """Transcription succeeded but no row exists → nothing will ever point here."""
    wav = _wav(tmp_path / "noinsert.wav")
    monkeypatch.setattr(main, "paste_text", lambda t: True)
    app = _app(_DB(fail=True))

    main.SFlowApp._on_transcription_done(app, "hola", 1.0, "m1", wav)

    assert not os.path.exists(wav)


def test_overlapping_dictations_do_not_cross_wires(tmp_path, monkeypatch):
    """Two dictations in flight: each row must keep ITS OWN WAV.

    With the path held in an instance attribute, worker B overwrote it before
    slot A ran — row A got B's WAV (so "Re-transcribir" on A would rewrite A's
    text with B's audio) and A's WAV became an orphan.
    """
    wav_a, wav_b = _wav(tmp_path / "a.wav"), _wav(tmp_path / "b.wav")
    monkeypatch.setattr(main, "paste_text", lambda t: True)
    db = _DB()
    emitted = []
    app = _app(db, transcription_done=types.SimpleNamespace(emit=lambda *a: emitted.append(a)))

    # Both workers finish before either queued slot runs — the real interleaving.
    app.transcriber = types.SimpleNamespace(transcribe=lambda buf: ("texto A", "m1"))
    main.SFlowApp._transcribe_worker(app, b"", 1.0, wav_a)
    app.transcriber = types.SimpleNamespace(transcribe=lambda buf: ("texto B", "m1"))
    main.SFlowApp._transcribe_worker(app, b"", 1.0, wav_b)
    for args in emitted:
        main.SFlowApp._on_transcription_done(app, *args)

    by_text = {r["text"]: r["audio_path"] for r in db.rows}
    assert by_text == {"texto A": wav_a, "texto B": wav_b}
    assert os.path.exists(wav_a) and os.path.exists(wav_b)


def test_discard_audio_tolerates_missing_and_none(tmp_path):
    main._discard_audio(None)
    main._discard_audio(str(tmp_path / "never-existed.wav"))


# ---- (c) mtime sweep: the safety net for orphans already on disk ----

def test_sweep_deletes_old_orphan_keeps_recent(tmp_path):
    db = TranscriptionDB(str(tmp_path / "t.db"))
    audio = tmp_path / "audio"
    audio.mkdir()
    old = _wav(audio / "old.wav")
    _age(old, 30)
    fresh = _wav(audio / "fresh.wav")  # stands in for a dictation in flight

    orphans = db.prune_orphan_audio_files(str(audio), days=7)

    assert orphans == [old]
    assert os.path.exists(fresh), "an in-flight dictation's WAV must not be swept"


def test_sweep_never_touches_a_referenced_wav(tmp_path):
    """Guards "re-transcribir desde el historial": a live row's WAV stays put."""
    db = TranscriptionDB(str(tmp_path / "t.db"))
    audio = tmp_path / "audio"
    audio.mkdir()
    kept = _wav(audio / "referenced.wav")
    _age(kept, 30)
    db.insert("hola", audio_path=kept)

    assert db.prune_orphan_audio_files(str(audio), days=7) == []


def test_sweep_ignores_non_wav_and_missing_dir(tmp_path):
    db = TranscriptionDB(str(tmp_path / "t.db"))
    audio = tmp_path / "audio"
    audio.mkdir()
    other = audio / "notes.txt"
    other.write_text("x")
    _age(str(other), 30)

    assert db.prune_orphan_audio_files(str(audio), days=7) == []
    assert db.prune_orphan_audio_files(str(tmp_path / "gone"), days=7) == []


def test_row_prune_and_sweep_together_clear_everything(tmp_path):
    """The two passes compose: the row-driven prune un-references an old WAV, the
    sweep collects the orphan the DB never knew about."""
    db = TranscriptionDB(str(tmp_path / "t.db"))
    audio = tmp_path / "audio"
    audio.mkdir()
    referenced = _wav(audio / "referenced.wav")
    orphan = _wav(audio / "orphan.wav")
    _age(referenced, 30)
    _age(orphan, 30)
    import sqlite3
    with sqlite3.connect(db.db_path) as c:
        c.execute(
            "INSERT INTO transcriptions (text, audio_path, created_at) VALUES (?,?,?)",
            ("vieja", referenced, "2020-01-01 10:00:00"),
        )

    for p in db.prune_old_audio_paths(days=7):
        main._discard_audio(p)
    for p in db.prune_orphan_audio_files(str(audio), days=7):
        main._discard_audio(p)

    assert os.listdir(audio) == []
