"""The Hub renders in the active language — instantiated headless (offscreen)
with language=es and language=en."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import config  # noqa: E402
from db.database import TranscriptionDB  # noqa: E402
from ui.hub_window import HubWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _hub(tmp_path, lang):
    config.set_setting("language", lang)
    db = TranscriptionDB(str(tmp_path / "t.db"))
    return HubWindow(db)


def test_hub_sidebar_is_spanish(qapp, tmp_path):
    hub = _hub(tmp_path, "es")
    assert "Historial" in hub.btn_hist.text()
    assert "Ajustes" in hub.btn_set.text()


def test_hub_sidebar_is_english(qapp, tmp_path):
    hub = _hub(tmp_path, "en")
    assert "History" in hub.btn_hist.text()
    assert "Settings" in hub.btn_set.text()
