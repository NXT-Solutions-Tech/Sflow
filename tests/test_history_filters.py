"""History filters: by app, by model, by recency (the F4 filter dropdowns)."""
import sqlite3
from datetime import datetime, timedelta, timezone

from db.database import TranscriptionDB


def test_filter_by_app(tmp_path):
    db = TranscriptionDB(str(tmp_path / "t.db"))
    db.insert("a", app="Notes", model="whisper-x")
    db.insert("b", app="Slack", model="groq")
    assert {r["text"] for r in db.query(app="Notes")} == {"a"}


def test_filter_by_model(tmp_path):
    db = TranscriptionDB(str(tmp_path / "t.db"))
    db.insert("a", app="Notes", model="whisper-x")
    db.insert("b", app="Slack", model="groq")
    assert {r["text"] for r in db.query(model="groq")} == {"b"}


def test_no_filter_returns_all(tmp_path):
    db = TranscriptionDB(str(tmp_path / "t.db"))
    db.insert("a")
    db.insert("b")
    assert len(db.query()) == 2


def test_distinct_apps_and_models(tmp_path):
    db = TranscriptionDB(str(tmp_path / "t.db"))
    db.insert("a", app="Notes", model="whisper-x")
    db.insert("b", app="Slack", model="groq")
    assert set(db.distinct_apps()) == {"Notes", "Slack"}
    assert set(db.distinct_models()) == {"whisper-x", "groq"}


def test_filter_by_recency(tmp_path):
    db = TranscriptionDB(str(tmp_path / "t.db"))
    db.insert("recent")
    old = (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(db.db_path) as c:
        c.execute(
            "INSERT INTO transcriptions (text, word_count, created_at) VALUES (?,?,?)",
            ("old", 1, old),
        )
    assert {r["text"] for r in db.query(since_days=30)} == {"recent"}
