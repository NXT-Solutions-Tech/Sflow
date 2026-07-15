#!/usr/bin/env python3
"""Offscreen light+dark preview harness for SFlow's UI surfaces.

Renders every themed surface to a PNG in BOTH schemes so the visual refactor can
be reviewed without a display. Run with the repo venv:

    QT_QPA_PLATFORM=offscreen venv/bin/python scripts/preview_surfaces.py

PNGs land in <scratchpad>/previews/ (or ./previews/ if no scratchpad env).

Native NSPanel setup (pill / red dot) and blocking QMessageBox calls are stubbed
so surfaces instantiate headless.
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# repo root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Isolate user data: point the DB / settings at a temp dir BEFORE importing app code.
_TMP = tempfile.mkdtemp(prefix="sflow_preview_")
os.environ["HOME"] = os.environ.get("HOME", _TMP)  # keep real HOME; just be safe

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402
from PyQt6.QtCore import QSize  # noqa: E402

from ui import theme  # noqa: E402


OUT = os.path.join(
    os.environ.get("CLAUDE_SCRATCHPAD", os.path.join(ROOT, "previews")),
    "previews",
) if os.environ.get("CLAUDE_SCRATCHPAD") else os.path.join(ROOT, "previews")
os.makedirs(OUT, exist_ok=True)


def _stub_natives():
    """No-op the native NSPanel setup + blocking dialogs."""
    from ui import pill_widget, red_dot_indicator
    pill_widget.PillWidget._setup_native_macos = lambda self: None
    if hasattr(pill_widget.PillWidget, "_try_install_visual_effect"):
        pill_widget.PillWidget._try_install_visual_effect = lambda self: None
    red_dot_indicator.RedDotIndicator._setup_native_macos = lambda self: None
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)


def _temp_db():
    from db.database import TranscriptionDB
    return TranscriptionDB(os.path.join(_TMP, "preview.db")) if _db_takes_path() else TranscriptionDB()


def _db_takes_path():
    import inspect
    from db.database import TranscriptionDB
    try:
        sig = inspect.signature(TranscriptionDB.__init__)
        return len(sig.parameters) > 1
    except (TypeError, ValueError):
        return False


def _seed(db):
    """Insert a few sample transcriptions so content pages render for review."""
    try:
        if db.get_recent(limit=1):
            return
        samples = [
            ("Recuérdame enviar el reporte de ventas antes de las cinco.", "es", 3.2, "Slack"),
            ("Let's schedule the design review for Thursday morning.", "en", 2.8, "Gmail"),
            ("Nueva línea. El plan de la semana quedó listo, dale enter.", "es", 4.1, "Notes"),
            ("This is a longer dictation to test how the card preview truncates "
             "and expands when the text runs well past the fold in the history list.",
             "en", 7.5, "VS Code"),
        ]
        for text, lang, dur, app in samples:
            db.insert(text, language=lang, duration_seconds=dur, model="whisper-turbo-local", app=app)
    except Exception as e:
        print(f"  (seed skipped: {e})")


def _grab(widget, name, scheme):
    # Respect the size the caller already set; only fall back if unsized.
    if widget.width() < 40 or widget.height() < 40:
        hint = widget.sizeHint()
        widget.resize(hint if hint.isValid() else QSize(880, 620))
    widget.ensurePolished()
    QApplication.processEvents()  # flush layout/paint so nested pages capture clean
    pm = widget.grab()
    path = os.path.join(OUT, f"{name}_{scheme}.png")
    pm.save(path)
    print(f"  saved {os.path.relpath(path, ROOT)}  ({pm.width()}x{pm.height()})")


def build_surfaces(scheme):
    """Return a list of (name, widget) freshly built under the active scheme."""
    from ui.hub_window import HubWindow
    from ui.pill_widget import PillWidget
    from ui.red_dot_indicator import RedDotIndicator
    import main as sflow_main

    surfaces = []

    db = _temp_db()
    _seed(db)
    hub = HubWindow(db)
    hub.resize(880, 620)
    surfaces.append(("hub", hub))

    # Individual Hub pages, built fresh & standalone (detached from the stack)
    # so each grabs at a clean, readable size.
    from ui.hub_window import (
        HomePage, InsightsPage, HistoryPage, DictionaryPage,
        SnippetsPage, TransformsPage, SettingsPage,
    )
    page_ctors = [
        (lambda: HomePage(db), "page_home"),
        (lambda: InsightsPage(db), "page_insights"),
        (lambda: HistoryPage(db), "page_history"),
        (lambda: DictionaryPage(), "page_dictionary"),
        (lambda: SnippetsPage(), "page_snippets"),
        (lambda: TransformsPage(), "page_transforms"),
        (lambda: SettingsPage(), "page_settings"),
    ]
    from PyQt6.QtWidgets import QWidget, QVBoxLayout
    bg = theme.tokens(theme.active_scheme())["bg"]
    for ctor, nm in page_ctors:
        try:
            pg = ctor()
            if hasattr(pg, "reload"):
                pg.reload()  # fresh page → first population, no duplicates
            # Wrap in a themed background so the standalone grab matches the Hub.
            holder = QWidget()
            holder.setObjectName("holder")
            holder.setStyleSheet(f"#holder {{ background: {bg}; }}")
            lay = QVBoxLayout(holder)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(pg)
            holder.resize(700, 620)
            surfaces.append((nm, holder))
        except Exception as e:
            print(f"  (skip {nm}: {e})")

    # FirstRunDialog
    try:
        frd = sflow_main.FirstRunDialog()
        surfaces.append(("first_run", frd))
    except Exception as e:  # pragma: no cover
        print(f"  (skip FirstRunDialog: {e})")

    # Pill (idle) + RedDot
    try:
        pill = PillWidget()
        pill.resize(120, 40)
        surfaces.append(("pill", pill))
    except Exception as e:
        print(f"  (skip pill: {e})")
    try:
        dot = RedDotIndicator()
        dot.resize(24, 24)
        surfaces.append(("red_dot", dot))
    except Exception as e:
        print(f"  (skip red_dot: {e})")

    return surfaces


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    _stub_natives()
    theme.load_fonts()

    for scheme in ("light", "dark"):
        print(f"[{scheme}]")
        theme.set_active_scheme(scheme)
        app.setStyleSheet(theme.qss(scheme))
        for name, widget in build_surfaces(scheme):
            try:
                _grab(widget, name, scheme)
            except Exception as e:  # pragma: no cover
                print(f"  ERROR grabbing {name}: {e}")

    print(f"\nPreviews in: {OUT}")


if __name__ == "__main__":
    main()
