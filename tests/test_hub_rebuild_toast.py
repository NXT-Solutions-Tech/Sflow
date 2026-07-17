"""F4 UI: rebuild_pages() preserves state, and the in-app ToastManager queues.
Headless (offscreen)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from db.database import TranscriptionDB  # noqa: E402
from ui.hub_window import HubWindow  # noqa: E402
from ui.toast import ToastManager  # noqa: E402
from core import error_messages as em  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# ---------- rebuild_pages ----------
def test_rebuild_preserves_active_page_and_search(qapp, tmp_path):
    db = TranscriptionDB(str(tmp_path / "t.db"))
    hub = HubWindow(db)
    hub.pages.setCurrentIndex(2)              # History
    hub.history_page.search.setText("foo")

    hub.rebuild_pages()                       # must not crash

    assert hub.pages.count() == 7
    assert hub.pages.currentIndex() == 2      # active page preserved
    assert hub.history_page.search.text() == "foo"  # and its search text


# ---------- ToastManager ----------
def test_toast_shows_and_queues(qapp):
    tm = ToastManager(duration_ms=5000)
    tm.show(em.message_for(em.CODE_OFFLINE))
    assert tm._showing is True                # first one is displayed
    tm.show(em.message_for(em.CODE_TIMEOUT))
    assert len(tm._queue) == 1                # second waits its turn


def test_toast_never_raises_without_content(qapp):
    tm = ToastManager()
    tm.show(em.message_for(em.CODE_MODEL_MISSING))  # exercises widget creation
