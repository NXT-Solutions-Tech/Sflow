"""DB migration + insights (word_count, per-app, WPM, streak, legacy backfill)."""
import sqlite3
from datetime import date, timedelta
from db.database import TranscriptionDB


def test_migration_adds_columns(tmp_path):
    db = TranscriptionDB(str(tmp_path / "t.db"))
    cols = [r[1] for r in sqlite3.connect(db.db_path).execute("PRAGMA table_info(transcriptions)").fetchall()]
    assert "app" in cols and "word_count" in cols and "audio_path" in cols


def test_insert_wordcount_and_insights(tmp_path):
    db = TranscriptionDB(str(tmp_path / "t.db"))
    db.insert("una dos tres cuatro cinco", duration_seconds=3.0, app="Notes")
    db.insert("uno dos", duration_seconds=1.0, app="Slack")
    d = db.insights()
    assert d["count"] == 2
    assert d["words"] == 7
    assert d["wpm"] > 0
    apps = {a["app"]: a["n"] for a in d["per_app"]}
    assert apps["Notes"] == 1 and apps["Slack"] == 1


def test_streak_counts_consecutive_days(tmp_path):
    db = TranscriptionDB(str(tmp_path / "t.db"))
    db.insert("hoy dicto esto", duration_seconds=1.0, app="X")
    with sqlite3.connect(db.db_path) as c:
        for i in (1, 2):
            day = (date.today() - timedelta(days=i)).isoformat()
            c.execute(
                "INSERT INTO transcriptions (text, duration_seconds, app, word_count, created_at) VALUES (?,?,?,?,?)",
                ("x", 1.0, "X", 1, day + " 10:00:00"),
            )
    assert db.insights()["streak"] == 3


def test_legacy_backfill_word_count(tmp_path):
    p = str(tmp_path / "legacy.db")
    with sqlite3.connect(p) as c:
        c.execute(
            "CREATE TABLE transcriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, "
            "language TEXT, duration_seconds REAL, model TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        c.execute("INSERT INTO transcriptions (text) VALUES ('una dos tres')")
    TranscriptionDB(p)  # runs migration + backfill
    wc = sqlite3.connect(p).execute("SELECT word_count FROM transcriptions").fetchone()[0]
    assert wc == 3
