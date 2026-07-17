"""DB robustness: corrupt-file recovery, WAL + busy_timeout, 0600 perms.

A corrupt history used to crash the app at launch — the failure was in
TranscriptionDB.__init__, which the excepthook doesn't cover.
"""
import os
import sqlite3

from db.database import TranscriptionDB
from db.snippets import SnippetsDB


def test_corrupt_db_is_quarantined_and_recreated(tmp_path):
    p = tmp_path / "t.db"
    p.write_bytes(b"this is definitely not a sqlite database, just garbage" * 8)

    db = TranscriptionDB(str(p))

    assert db.recovered_from_corruption is True
    # The corrupt bytes are kept aside for recovery tooling, not deleted.
    corrupts = list(tmp_path.glob("t.db.corrupt-*"))
    assert len(corrupts) == 1
    # And the fresh DB actually works.
    assert db.insert("hola", duration_seconds=1.0) >= 1
    assert db.count() == 1


def test_a_healthy_db_is_not_flagged(tmp_path):
    db = TranscriptionDB(str(tmp_path / "t.db"))
    assert db.recovered_from_corruption is False


def test_db_is_in_wal_mode(tmp_path):
    db = TranscriptionDB(str(tmp_path / "t.db"))
    db.insert("x", duration_seconds=1.0)
    with sqlite3.connect(db.db_path) as c:
        mode = c.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_db_file_is_0600(tmp_path):
    db = TranscriptionDB(str(tmp_path / "t.db"))
    assert oct(os.stat(db.db_path).st_mode & 0o777) == "0o600"


def test_snippets_share_wal_mode(tmp_path):
    s = SnippetsDB(str(tmp_path / "s.db"))
    s.add("mi correo", "yo@example.com")
    with sqlite3.connect(s.db_path) as c:
        mode = c.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
