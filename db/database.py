import sqlite3
import time
from contextlib import closing
from datetime import date, timedelta
from config import DB_PATH


def _compute_streak(per_day: dict) -> int:
    """Consecutive days (ending today, or yesterday) with ≥1 dictation."""
    if not per_day:
        return 0
    d = date.today()
    if d.isoformat() not in per_day:
        d = d - timedelta(days=1)
        if d.isoformat() not in per_day:
            return 0
    streak = 0
    while d.isoformat() in per_day:
        streak += 1
        d -= timedelta(days=1)
    return streak


class TranscriptionDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    language TEXT,
                    duration_seconds REAL,
                    model TEXT DEFAULT 'whisper-large-v3-turbo',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transcriptions_created_at
                ON transcriptions(created_at)
            """)
            # Migration: add audio_path if missing (allows retry from history)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(transcriptions)").fetchall()]
            if "audio_path" not in cols:
                conn.execute("ALTER TABLE transcriptions ADD COLUMN audio_path TEXT")
            # M6: per-app usage + word_count for Insights
            if "app" not in cols:
                conn.execute("ALTER TABLE transcriptions ADD COLUMN app TEXT")
            if "word_count" not in cols:
                conn.execute("ALTER TABLE transcriptions ADD COLUMN word_count INTEGER")
                for rid, txt in conn.execute("SELECT id, text FROM transcriptions").fetchall():
                    conn.execute("UPDATE transcriptions SET word_count = ? WHERE id = ?",
                                 (len((txt or "").split()), rid))

    def insert(self, text: str, language: str = None, duration_seconds: float = None,
               model: str = "whisper-large-v3-turbo", audio_path: str = None,
               app: str = None) -> int:
        word_count = len((text or "").split())
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            cursor = conn.execute(
                "INSERT INTO transcriptions (text, language, duration_seconds, model, audio_path, app, word_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (text, language, duration_seconds, model, audio_path, app, word_count),
            )
            return cursor.lastrowid

    def insights(self) -> dict:
        """Aggregate stats for the Insights page: totals, WPM, per-app, streak, per-day."""
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            t = conn.execute(
                "SELECT COUNT(*) c, COALESCE(SUM(word_count),0) w, COALESCE(SUM(duration_seconds),0) s "
                "FROM transcriptions"
            ).fetchone()
            count, words, seconds = t["c"], t["w"], t["s"]
            wpm = (words / (seconds / 60.0)) if seconds and seconds > 0 else 0.0
            per_app = [dict(r) for r in conn.execute(
                "SELECT COALESCE(NULLIF(app,''),'(desconocida)') app, COUNT(*) n, COALESCE(SUM(word_count),0) w "
                "FROM transcriptions GROUP BY 1 ORDER BY n DESC LIMIT 8"
            ).fetchall()]
            per_day = {r["d"]: r["n"] for r in conn.execute(
                "SELECT date(created_at,'localtime') d, COUNT(*) n FROM transcriptions GROUP BY d"
            ).fetchall()}
        return {
            "count": count, "words": words, "seconds": seconds, "wpm": wpm,
            "per_app": per_app, "per_day": per_day, "streak": _compute_streak(per_day),
        }

    def update_text(self, row_id: int, new_text: str):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                "UPDATE transcriptions SET text = ? WHERE id = ?",
                (new_text, row_id),
            )

    def get_recent(self, limit: int = 20) -> list:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM transcriptions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get(self, row_id: int) -> dict | None:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute("SELECT * FROM transcriptions WHERE id = ?", (row_id,)).fetchone()
            return dict(r) if r else None

    def search(self, query: str, limit: int = 20) -> list:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM transcriptions WHERE text LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def count(self) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            return conn.execute("SELECT COUNT(*) FROM transcriptions").fetchone()[0]

    def referenced_audio_paths(self) -> set[str]:
        """Every WAV a live row still points at — i.e. the ones "re-transcribir
        desde el historial" needs on disk."""
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            return {
                r[0] for r in conn.execute(
                    "SELECT audio_path FROM transcriptions WHERE audio_path IS NOT NULL"
                ).fetchall() if r[0]
            }

    def prune_orphan_audio_files(self, audio_dir: str, days: int = 7) -> list[str]:
        """Return WAVs in `audio_dir` older than `days` that NO row references.

        Safety net for the orphans left behind before the write-after-insert fix
        (and for any future path that drops a file without a row): the row-driven
        prune can't see them because it only walks audio_path columns. The mtime
        cutoff is what protects a dictation that is still in flight — its WAV was
        written seconds ago, so it can never be `days` old.
        """
        import os
        cutoff = time.time() - days * 86400
        referenced = self.referenced_audio_paths()
        orphans = []
        try:
            names = os.listdir(audio_dir)
        except OSError:
            return orphans
        for name in names:
            if not name.endswith(".wav"):
                continue
            path = os.path.join(audio_dir, name)
            if path in referenced:
                continue
            try:
                if os.path.getmtime(path) < cutoff:
                    orphans.append(path)
            except OSError:
                continue
        return orphans

    def prune_old_audio_paths(self, days: int = 7) -> list[str]:
        """Return paths of WAVs older than `days` so caller can unlink them. Clears audio_path in DB."""
        import os
        from datetime import datetime, timedelta, timezone
        # Match SQLite's CURRENT_TIMESTAMP format ("YYYY-MM-DD HH:MM:SS", space
        # separator, no microseconds) so the string comparison is correct.
        # It must stay UTC, like CURRENT_TIMESTAMP: a local-time cutoff would
        # silently prune the wrong window by the UTC offset.
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            rows = conn.execute(
                "SELECT id, audio_path FROM transcriptions WHERE audio_path IS NOT NULL AND created_at < ?",
                (cutoff,),
            ).fetchall()
            paths = [r[1] for r in rows if r[1] and os.path.exists(r[1])]
            if rows:
                conn.execute(
                    "UPDATE transcriptions SET audio_path = NULL WHERE audio_path IS NOT NULL AND created_at < ?",
                    (cutoff,),
                )
        return paths
