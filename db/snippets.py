"""Snippets store — voice triggers → text expansions.

Example: trigger "mi correo" → expansion is whatever email the user saves.
After transcription, any trigger matching (case-insensitive, word-boundary)
is replaced inline by its expansion.

The table ships EMPTY on purpose — do not seed defaults. An expansion is pasted
verbatim into whatever the user is writing, so a seeded value is either someone
else's real data or a placeholder that gets pasted for real. The Hub's snippets
page teaches the feature and renders its own empty state.
"""
import sqlite3
from contextlib import closing
from config import DB_PATH


class SnippetsDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init()

    def _connect(self) -> sqlite3.Connection:
        """WAL + busy timeout, matching TranscriptionDB — snippets share the same
        file, so a snippet write must not raise "database is locked" when a
        dictation is inserting at the same moment."""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init(self):
        with closing(self._connect()) as conn, conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snippets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigger TEXT NOT NULL,
                    expansion TEXT NOT NULL,
                    usage_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_trigger ON snippets(trigger)")

    def list_all(self) -> list[dict]:
        with closing(self._connect()) as conn, conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM snippets ORDER BY usage_count DESC, trigger"
            ).fetchall()
            return [dict(r) for r in rows]

    def add(self, trigger: str, expansion: str) -> int:
        trigger = (trigger or "").strip().lower()
        expansion = expansion or ""
        if not trigger or not expansion:
            raise ValueError("trigger y expansion son requeridos")
        with closing(self._connect()) as conn, conn:
            c = conn.execute(
                "INSERT INTO snippets (trigger, expansion) VALUES (?, ?)",
                (trigger, expansion),
            )
            return c.lastrowid

    def update(self, snippet_id: int, trigger: str, expansion: str):
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE snippets SET trigger = ?, expansion = ? WHERE id = ?",
                (trigger.strip().lower(), expansion, snippet_id),
            )

    def delete(self, snippet_id: int):
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))

    def increment_usage(self, snippet_id: int):
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE snippets SET usage_count = usage_count + 1 WHERE id = ?",
                (snippet_id,),
            )
