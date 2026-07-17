"""The pill remembers where it was dragged (setting round-trip)."""
import pytest

pytest.importorskip("PyQt6.QtWidgets")

import config  # noqa: E402
import ui.pill_widget as pw  # noqa: E402


def test_default_is_none():
    assert pw.load_pill_pos() is None


def test_round_trip():
    pw.save_pill_pos(120, 340)
    assert pw.load_pill_pos() == (120, 340)


def test_garbage_is_ignored():
    config.set_setting("pill_pos", "nonsense")
    assert pw.load_pill_pos() is None
    config.set_setting("pill_pos", [1])  # wrong length
    assert pw.load_pill_pos() is None
