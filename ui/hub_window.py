"""Hub window — Wispr Flow-style dashboard with sidebar + history.

Opened from the tray menu or Cmd+Shift+H. Non-activating — doesn't steal
focus from the app the user is working in (uses native NSPanel behavior
like the pill).
"""
from datetime import datetime, timezone
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QStackedWidget, QListWidget, QListWidgetItem,
    QMenu, QPlainTextEdit, QGroupBox, QCheckBox, QComboBox, QDialog,
    QApplication, QMessageBox, QSizePolicy, QFileDialog, QTabWidget,
)
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QAction, QPixmap, QFont, QPainter, QColor, QPen
from db.database import TranscriptionDB
from db.snippets import SnippetsDB
from core.paste import paste_last_transcript
from core.relaunch import relaunch_app
from config import (
    LOGO_PATH, DICTIONARY_PATH, get_setting, set_setting, STT_MODELS,
)
from core.recorder import list_input_devices
from core.secrets import set_key, key_source
from core.models import ModelManager, missing_code_for_selection
from core import error_messages
from core.i18n import tr

_STT_BY_ID = {m["id"]: m for m in STT_MODELS}
import os
import subprocess


# ---------- Color palette ----------
# Live theme proxy: C.BG / C.ACCENT / … resolve against the active light|dark
# scheme (see ui/theme.py). Keeps the legacy token API so existing inline
# stylesheets become theme-aware for free.
from ui.theme import C  # noqa: E402
from ui import icons  # noqa: E402
from ui.components import Switch, page_title, primary_button, secondary_button  # noqa: E402


# ---------- Helpers ----------
def time_ago(iso_ts: str) -> str:
    try:
        if not iso_ts:
            return ""
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        s = int(delta.total_seconds())
        if s < 60:
            return "hace un momento"
        if s < 3600:
            return f"hace {s // 60}m"
        if s < 86400:
            return f"hace {s // 3600}h"
        if s < 604800:
            return f"hace {s // 86400}d"
        return dt.strftime("%d %b")
    except Exception:
        return iso_ts or ""


class EditTranscriptDialog(QDialog):
    """Edit a past transcription. After save, suggest new words (capitalized /
    hyphenated) to add to dictionary.txt for future Whisper boosting."""
    saved = pyqtSignal(int)  # row id

    def __init__(self, row_id: int, original_text: str):
        super().__init__()
        self.row_id = row_id
        self.original = original_text
        self.setWindowTitle("Editar transcripción")
        self.resize(580, 340)
        self.setStyleSheet(f"background: {C.BG}; color: {C.TEXT};")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        lbl = QLabel("Corrige el texto. SFlow sugiere automáticamente palabras nuevas (nombres, jerga) para el diccionario.")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px;")
        root.addWidget(lbl)

        self.editor = QPlainTextEdit()
        self.editor.setPlainText(original_text)
        root.addWidget(self.editor, 1)

        row = QHBoxLayout()
        row.addStretch()
        cancel = secondary_button("Cancelar")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)

        save = primary_button("Guardar")
        save.setDefault(True)
        save.clicked.connect(self._save)
        row.addWidget(save)
        root.addLayout(row)

    def _save(self):
        new_text = self.editor.toPlainText().strip()
        if not new_text or new_text == self.original:
            self.accept()
            return

        from core.dictionary_learner import diff_candidates, add_to_dictionary
        from db.database import TranscriptionDB

        TranscriptionDB().update_text(self.row_id, new_text)

        candidates = diff_candidates(self.original, new_text)
        if candidates:
            msg = QMessageBox(self)
            msg.setWindowTitle("Palabras detectadas")
            msg.setText("Detectamos estas palabras nuevas en tu corrección:\n\n"
                        + "\n".join(f"  • {c}" for c in candidates[:10])
                        + "\n\n¿Agregarlas al diccionario personal? (mejora reconocimiento futuro)")
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg.setDefaultButton(QMessageBox.StandardButton.Yes)
            if msg.exec() == QMessageBox.StandardButton.Yes:
                add_to_dictionary(candidates)

        self.saved.emit(self.row_id)
        self.accept()


class SidebarButton(QPushButton):
    def __init__(self, icon_name: str, label: str):
        super().__init__(f"  {label}")
        self._icon_name = icon_name
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(38)
        self.setIcon(icons.icon(icon_name, color=C.TEXT_DIM, size=18))
        self.setIconSize(QSize(18, 18))
        self.setStyleSheet(f"""
            QPushButton {{
                text-align: left;
                padding: 7px 12px;
                border: none;
                border-radius: 8px;
                color: {C.TEXT_DIM};
                background: transparent;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {C.BG_HOVER};
                color: {C.TEXT};
            }}
            QPushButton:checked {{
                background: {C.BG_CARD};
                color: {C.TEXT};
                font-weight: 600;
            }}
        """)
        self.toggled.connect(self._retint)

    def _retint(self, checked: bool):
        self.setIcon(icons.icon(self._icon_name, color=(C.TEXT if checked else C.TEXT_DIM), size=18))


class TranscriptionCard(QFrame):
    delete_requested = pyqtSignal(int)
    copy_requested = pyqtSignal(str)
    repaste_requested = pyqtSignal(str)
    retry_requested = pyqtSignal(int)

    def __init__(self, row: dict):
        super().__init__()
        self._row = row
        self._id = row.get("id")
        self._text = row.get("text", "") or ""
        self._model = row.get("model", "") or ""
        self._duration = row.get("duration_seconds") or 0.0
        self._created = row.get("created_at", "") or ""
        self._audio_path = row.get("audio_path") or ""
        self._expanded = False

        self.setStyleSheet(f"""
            TranscriptionCard {{
                background: {C.BG_CARD};
                border-radius: 10px;
                border: 1px solid {C.DIVIDER};
            }}
            TranscriptionCard:hover {{
                border-color: {C.BG_HOVER};
            }}
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        root = QVBoxLayout()
        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(6)

        # Header: time · model · duration
        head = QHBoxLayout()
        head.setSpacing(6)
        meta = QLabel(self._meta_line())
        meta.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px;")
        head.addWidget(meta)
        head.addStretch()

        menu_btn = QPushButton()
        menu_btn.setIcon(icons.icon("more", color=C.TEXT_DIM, size=16))
        menu_btn.setIconSize(QSize(16, 16))
        menu_btn.setFixedSize(24, 24)
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C.BG_HOVER}; }}
        """)
        menu_btn.clicked.connect(self._show_menu)
        head.addWidget(menu_btn)
        root.addLayout(head)

        # Body text
        self._text_label = QLabel(self._preview())
        self._text_label.setWordWrap(True)
        self._text_label.setStyleSheet(f"color: {C.TEXT}; font-size: 13px; line-height: 1.45;")
        self._text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self._text_label)

        self.setLayout(root)

    def _meta_line(self) -> str:
        parts = [time_ago(self._created)]
        if self._duration:
            parts.append(f"{self._duration:.1f}s")
        if self._model:
            # shorten long model ids
            m = self._model
            if "/" in m:
                m = m.split("/")[-1]
            parts.append(m)
        return " · ".join(p for p in parts if p)

    def _preview(self) -> str:
        t = self._text
        if self._expanded or len(t) <= 220:
            return t
        return t[:220].rstrip() + "…"

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._expanded = not self._expanded
            self._text_label.setText(self._preview())

    def _show_menu(self):
        m = QMenu(self)
        m.setStyleSheet(f"""
            QMenu {{
                background: {C.BG_CARD}; color: {C.TEXT};
                border: 1px solid {C.DIVIDER}; border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {C.BG_HOVER}; }}
        """)
        a_copy = QAction("Copiar al portapapeles", m)
        a_copy.triggered.connect(lambda: self.copy_requested.emit(self._text))
        m.addAction(a_copy)

        a_repaste = QAction("Re-pegar en cursor activo", m)
        a_repaste.triggered.connect(lambda: self.repaste_requested.emit(self._text))
        m.addAction(a_repaste)

        a_edit = QAction("Editar y aprender al diccionario", m)
        a_edit.triggered.connect(self._open_edit)
        m.addAction(a_edit)

        import os
        if self._audio_path and os.path.exists(self._audio_path):
            a_retry = QAction("Re-transcribir audio", m)
            a_retry.triggered.connect(lambda: self.retry_requested.emit(self._id))
            m.addAction(a_retry)

        m.addSeparator()
        a_del = QAction("Eliminar", m)
        a_del.triggered.connect(lambda: self.delete_requested.emit(self._id))
        m.addAction(a_del)
        m.exec(self.mapToGlobal(self.rect().topRight()))

    def _open_edit(self):
        dlg = EditTranscriptDialog(self._id, self._text)
        dlg.saved.connect(self.retry_requested.emit)  # piggyback reload
        dlg.exec()


class HistoryPage(QWidget):
    def __init__(self, db: TranscriptionDB):
        super().__init__()
        self.db = db
        self._all_rows: list[dict] = []

        root = QVBoxLayout()
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(14)

        title = page_title(tr("page.history"))
        root.addWidget(title)

        sub = QLabel("Tus transcripciones recientes. Click en una para expandir, ⋮ para acciones.")
        sub.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px;")
        root.addWidget(sub)

        # Search + refresh
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar transcripciones…")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(
            icons.icon("search", color=C.TEXT_FAINT, size=16),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.search.textChanged.connect(self._filter)
        row.addWidget(self.search)

        # Filters: app / model / recency. Selecting one re-queries the DB.
        self.filter_app = QComboBox()
        self.filter_model = QComboBox()
        self.filter_date = QComboBox()
        self.filter_date.addItem(tr("filter.all_time"), None)
        self.filter_date.addItem(tr("filter.today"), 1)
        self.filter_date.addItem(tr("filter.7d"), 7)
        self.filter_date.addItem(tr("filter.30d"), 30)
        for cb in (self.filter_app, self.filter_model, self.filter_date):
            cb.currentIndexChanged.connect(lambda _i: self.reload())
            row.addWidget(cb)

        refresh = QPushButton()
        refresh.setObjectName("icon")
        refresh.setIcon(icons.icon("refresh", color=C.TEXT_DIM, size=16))
        refresh.setIconSize(QSize(16, 16))
        refresh.setFixedSize(36, 36)
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.reload)
        row.addWidget(refresh)

        root.addLayout(row)

        # Scroll area with cards
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setSpacing(8)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(self._list_container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 8px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {C.DIVIDER}; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {C.BG_HOVER}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        root.addWidget(scroll, 1)

        self.setLayout(root)
        self.reload()

    def _sync_filter_options(self):
        """Repopulate the app/model dropdowns from what's in history, preserving
        the current selection. Signals are blocked so this can't re-trigger reload."""
        for cb, values, all_key in (
            (self.filter_app, self.db.distinct_apps(), "filter.all_apps"),
            (self.filter_model, self.db.distinct_models(), "filter.all_models"),
        ):
            prev = cb.currentData()
            cb.blockSignals(True)
            cb.clear()
            cb.addItem(tr(all_key), None)
            for v in values:
                cb.addItem(v, v)
            idx = cb.findData(prev)
            cb.setCurrentIndex(idx if idx >= 0 else 0)
            cb.blockSignals(False)

    def reload(self):
        self._sync_filter_options()
        self._all_rows = self.db.query(
            app=self.filter_app.currentData(),
            model=self.filter_model.currentData(),
            since_days=self.filter_date.currentData(),
            limit=500,
        )
        self._filter(self.search.text())

    def _filter(self, query: str):
        # Clear existing cards (keep stretch at end)
        while self._list_layout.count() > 1:
            w = self._list_layout.itemAt(0).widget()
            if w is None:
                break
            self._list_layout.removeWidget(w)
            w.deleteLater()

        q = (query or "").lower().strip()
        rows = self._all_rows
        if q:
            rows = [r for r in rows if q in (r.get("text") or "").lower()]

        if not rows:
            empty = QLabel("Nada por aquí. Dicta algo presionando Ctrl+Alt.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {C.TEXT_FAINT}; padding: 40px; font-size: 13px;")
            self._list_layout.insertWidget(0, empty)
            return

        for row in rows[:200]:
            card = TranscriptionCard(row)
            card.copy_requested.connect(self._copy_to_clipboard)
            card.repaste_requested.connect(self._repaste)
            card.delete_requested.connect(self._delete)
            card.retry_requested.connect(self._retry)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)

    def _copy_to_clipboard(self, text: str):
        QApplication.clipboard().setText(text)

    def _repaste(self, text: str):
        # Hide the hub so focus returns to the app underneath
        top = self.window()
        top.hide()
        QTimer.singleShot(180, lambda: paste_last_transcript(text))

    def _delete(self, row_id: int):
        import sqlite3, os
        from config import DB_PATH
        with sqlite3.connect(DB_PATH) as conn:
            r = conn.execute("SELECT audio_path FROM transcriptions WHERE id = ?", (row_id,)).fetchone()
            conn.execute("DELETE FROM transcriptions WHERE id = ?", (row_id,))
        if r and r[0] and os.path.exists(r[0]):
            try:
                os.unlink(r[0])
            except OSError:
                pass
        self.reload()

    def _retry(self, row_id: int):
        """Re-transcribe a past recording using the current backend/settings."""
        import os, io, threading
        from PyQt6.QtCore import QMetaObject, Qt as _Qt
        row = self.db.get(row_id)
        if not row or not row.get("audio_path") or not os.path.exists(row["audio_path"]):
            QMessageBox.warning(self, "Sin audio", "Este dictado no tiene WAV asociado.")
            return

        from core.transcriber import Transcriber
        transcriber = Transcriber()
        path = row["audio_path"]

        # Show feedback toast-style label at top of list
        busy = QLabel("Re-transcribiendo…")
        busy.setStyleSheet(f"color: {C.ACCENT}; padding: 8px; font-size: 12px;")
        self._list_layout.insertWidget(0, busy)

        def worker():
            try:
                with open(path, "rb") as f:
                    buf = io.BytesIO(f.read())
                new_text, model_id = transcriber.transcribe(buf)
                if new_text:
                    self.db.update_text(row_id, new_text)
            except Exception as e:
                print(f"retry failed: {e}")
            # Reload on main thread
            QTimer.singleShot(0, lambda: (busy.deleteLater() if busy else None, self.reload()))

        threading.Thread(target=worker, daemon=True).start()


class DictionaryPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout()
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(12)

        title = page_title(tr("page.dictionary"))
        root.addWidget(title)

        sub = QLabel("Una palabra o frase por línea (pista de vocabulario para Whisper: nombres, jerga, términos técnicos).\nPara sustituciones automáticas de texto usa una flecha:  btw -> by the way")
        sub.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        self.editor = QPlainTextEdit()
        self.editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {C.BG_INPUT}; color: {C.TEXT};
                border: 1px solid {C.DIVIDER}; border-radius: 8px;
                padding: 10px; font-family: 'SF Mono', Menlo, monospace;
                font-size: 13px;
            }}
        """)
        self._load()
        root.addWidget(self.editor, 1)

        row = QHBoxLayout()
        row.addStretch()
        save = primary_button("Guardar")
        save.clicked.connect(self._save)
        row.addWidget(save)
        root.addLayout(row)

        self.setLayout(root)

    def _load(self):
        try:
            if os.path.exists(DICTIONARY_PATH):
                with open(DICTIONARY_PATH) as f:
                    self.editor.setPlainText(f.read())
            else:
                from core.dictionary import _ensure_file
                _ensure_file()
                with open(DICTIONARY_PATH) as f:
                    self.editor.setPlainText(f.read())
        except Exception as e:
            self.editor.setPlainText(f"# Error loading: {e}")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(DICTIONARY_PATH), exist_ok=True)
            with open(DICTIONARY_PATH, "w") as f:
                f.write(self.editor.toPlainText())
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo guardar: {e}")


class SnippetsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.db = SnippetsDB()
        root = QVBoxLayout()
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(14)

        title = page_title(tr("page.snippets"))
        root.addWidget(title)

        sub = QLabel(
            'Atajos de voz. Cuando dictes el trigger, SFlow lo reemplaza por la expansión. '
            'Ejemplo: di "mi correo" y se pega tu email.'
        )
        sub.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # New snippet form
        form = QFrame()
        form.setObjectName("card")
        form.setStyleSheet(f"#card {{ background: {C.BG_CARD}; border: 1px solid {C.DIVIDER}; border-radius: 10px; }}")
        fl = QVBoxLayout(form)
        fl.setContentsMargins(14, 12, 14, 12)
        fl.setSpacing(8)

        lbl = QLabel("Agregar snippet")
        lbl.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 11px; font-weight: 500;")
        fl.addWidget(lbl)

        self.trigger_input = QLineEdit()
        self.trigger_input.setPlaceholderText("trigger (ej: mi correo)")
        fl.addWidget(self.trigger_input)

        self.expansion_input = QPlainTextEdit()
        self.expansion_input.setPlaceholderText("expansión (lo que se pega cuando digas el trigger)")
        self.expansion_input.setMaximumHeight(80)
        fl.addWidget(self.expansion_input)

        row = QHBoxLayout()
        row.addStretch()
        add_btn = primary_button("Agregar")
        add_btn.clicked.connect(self._add)
        row.addWidget(add_btn)
        fl.addLayout(row)
        root.addWidget(form)

        # List of existing snippets
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setSpacing(6)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(self._list_container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }}")
        root.addWidget(scroll, 1)

        self.setLayout(root)
        self.reload()

    def _add(self):
        t = self.trigger_input.text().strip()
        e = self.expansion_input.toPlainText().strip()
        if not t or not e:
            QMessageBox.warning(self, "Campos vacíos", "Trigger y expansión son requeridos.")
            return
        try:
            self.db.add(t, e)
            self.trigger_input.clear()
            self.expansion_input.clear()
            self.reload()
        except Exception as err:
            QMessageBox.warning(self, "Error", str(err))

    def reload(self):
        while self._list_layout.count() > 1:
            w = self._list_layout.itemAt(0).widget()
            if w is None:
                break
            self._list_layout.removeWidget(w)
            w.deleteLater()

        rows = self.db.list_all()
        if not rows:
            empty = QLabel("No tienes snippets. Agrega uno arriba.")
            empty.setStyleSheet(f"color: {C.TEXT_FAINT}; padding: 20px; text-align: center;")
            self._list_layout.insertWidget(0, empty)
            return

        for s in rows:
            card = self._snippet_card(s)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)

    def _snippet_card(self, s: dict) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        f.setStyleSheet(f"#card {{ background: {C.BG_CARD}; border: 1px solid {C.DIVIDER}; border-radius: 8px; }}")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(4)

        head = QHBoxLayout()
        trig = QLabel(f'"{s["trigger"]}"')
        trig.setStyleSheet(f"color: {C.ACCENT}; font-size: 13px; font-weight: 600;")
        head.addWidget(trig)

        if s.get("usage_count", 0) > 0:
            usage = QLabel(f"· usado {s['usage_count']}×")
            usage.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 11px;")
            head.addWidget(usage)

        head.addStretch()
        del_btn = QPushButton()
        del_btn.setIcon(icons.icon("x", color=C.TEXT_FAINT, size=14))
        del_btn.setIconSize(QSize(14, 14))
        del_btn.setFixedSize(24, 24)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C.BG_HOVER}; }}
        """)
        sid = s["id"]
        del_btn.clicked.connect(lambda: self._delete(sid))
        head.addWidget(del_btn)
        lay.addLayout(head)

        # Show expansion (multi-line safe)
        exp = QLabel(s["expansion"])
        exp.setWordWrap(True)
        exp.setStyleSheet(f"color: {C.TEXT}; font-size: 12px; line-height: 1.4;")
        lay.addWidget(exp)

        return f

    def _delete(self, sid: int):
        self.db.delete(sid)
        self.reload()


class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout()
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(16)

        title = page_title(tr("page.settings"))
        root.addWidget(title)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{
                background: transparent; color: {C.TEXT_DIM};
                padding: 8px 18px; margin-right: 2px; border: none;
                border-bottom: 2px solid transparent; font-size: 13px; font-weight: 500;
            }}
            QTabBar::tab:selected {{ color: {C.TEXT}; border-bottom: 2px solid {C.ACCENT}; }}
            QTabBar::tab:hover {{ color: {C.TEXT}; }}
        """)
        _general = QWidget(); gen = QVBoxLayout(_general)
        gen.setContentsMargins(2, 12, 2, 2); gen.setSpacing(14)
        gen.setAlignment(Qt.AlignmentFlag.AlignTop)
        _system = QWidget(); sysl = QVBoxLayout(_system)
        sysl.setContentsMargins(2, 12, 2, 2); sysl.setSpacing(14)
        sysl.setAlignment(Qt.AlignmentFlag.AlignTop)
        def _scrolled(inner_widget):
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.Shape.NoFrame)
            sa.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            sa.setWidget(inner_widget)
            return sa
        tabs.addTab(_scrolled(_general), "General")
        tabs.addTab(_scrolled(_system), "System")
        root.addWidget(tabs, 1)

        def group(name, target) -> QVBoxLayout:
            g = QGroupBox(name)
            g.setStyleSheet(f"""
                QGroupBox {{
                    color: {C.TEXT}; font-size: 13px; font-weight: 500;
                    border: 1px solid {C.DIVIDER}; border-radius: 10px;
                    padding-top: 20px; padding-bottom: 8px;
                    margin-top: 8px; background: {C.BG_CARD};
                }}
                QGroupBox::title {{
                    left: 14px; top: 0px; padding: 0 6px;
                }}
                QCheckBox {{ color: {C.TEXT}; font-size: 13px; padding: 6px 0; }}
                QCheckBox::indicator {{
                    width: 16px; height: 16px;
                    background: {C.BG_INPUT};
                    border: 1px solid {C.DIVIDER}; border-radius: 4px;
                }}
                QCheckBox::indicator:checked {{
                    background: {C.ACCENT}; border-color: {C.ACCENT};
                }}
                QLabel {{ color: {C.TEXT_DIM}; font-size: 12px; }}
                QComboBox {{
                    background: {C.BG_INPUT}; color: {C.TEXT};
                    border: 1px solid {C.DIVIDER}; border-radius: 6px;
                    padding: 6px 10px; min-width: 200px; font-size: 13px;
                }}
                QComboBox QAbstractItemView {{
                    background: {C.BG_CARD}; color: {C.TEXT};
                    selection-background-color: {C.BG_HOVER};
                    border: 1px solid {C.DIVIDER};
                }}
            """)
            inner = QVBoxLayout()
            inner.setContentsMargins(14, 8, 14, 10)
            inner.setSpacing(6)
            g.setLayout(inner)
            target.addWidget(g)
            return inner

        def dim(text):
            lb = QLabel(text)
            lb.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px; margin-top: 2px;")
            return lb

        # ============ GENERAL ============
        tl = group("Transcripción", gen)
        tl.addWidget(dim("Modelo de transcripción"))
        self.model_combo = QComboBox()
        for m in STT_MODELS:
            self.model_combo.addItem(m["label"], m["id"])
        self.model_combo.setCurrentIndex(max(0, self.model_combo.findData(get_setting("stt_model", "whisper-turbo-local"))))
        tl.addWidget(self.model_combo)

        # Download affordance: local models that ship as an on-demand download
        # (Whisper Turbo) show a "Descargar" button + status when not present. The
        # bundled Parakeet and cloud Groq never need it. See _refresh_model_dl().
        dlrow = QHBoxLayout()
        self.model_dl_status = dim("")
        dlrow.addWidget(self.model_dl_status)
        dlrow.addStretch()
        self.model_dl_btn = secondary_button(tr("settings.download"))
        self.model_dl_btn.clicked.connect(self._download_selected_model)
        dlrow.addWidget(self.model_dl_btn)
        tl.addLayout(dlrow)
        self.model_combo.currentIndexChanged.connect(lambda _i: self._refresh_model_dl())
        self._refresh_model_dl()

        tl.addWidget(dim("Idioma del dictado"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Auto — detecta ES/EN automáticamente", "auto")
        self.lang_combo.addItem("Español", "es")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.setCurrentIndex(max(0, self.lang_combo.findData(get_setting("stt_language", "auto"))))
        tl.addWidget(self.lang_combo)

        # App UI language (i18n) — distinct from the dictation language above.
        tl.addWidget(dim(tr("settings.language")))
        self.applang_combo = QComboBox()
        self.applang_combo.addItem(tr("settings.lang_auto"), "auto")
        self.applang_combo.addItem(tr("settings.lang_es"), "es")
        self.applang_combo.addItem(tr("settings.lang_en"), "en")
        self.applang_combo.setCurrentIndex(max(0, self.applang_combo.findData(get_setting("language", "auto"))))
        tl.addWidget(self.applang_combo)
        tl.addWidget(dim(tr("settings.lang_hint")))

        tl.addWidget(dim("Micrófono / entrada de audio"))
        self.mic_combo = QComboBox()
        self.mic_combo.addItem("Predeterminado del sistema", "")
        for d in list_input_devices():
            self.mic_combo.addItem(d["name"], d["name"])
        self.mic_combo.setCurrentIndex(max(0, self.mic_combo.findData(get_setting("input_device", "") or "")))
        tl.addWidget(self.mic_combo)

        al = group("Auto Cleanup", gen)
        al.addWidget(dim("Nivel de limpieza"))
        self.cleanup_combo = QComboBox()
        self.cleanup_combo.addItem("None — sin limpieza, texto verbatim", "none")
        self.cleanup_combo.addItem("Light — muletillas + puntuación", "light")
        self.cleanup_combo.addItem("Medium — claridad + concisión", "medium")
        self.cleanup_combo.setCurrentIndex(max(0, self.cleanup_combo.findData(get_setting("auto_cleanup_level", "none"))))
        al.addWidget(self.cleanup_combo)

        al.addWidget(dim("Proveedor de limpieza"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Groq · Llama (nube)", "groq")
        self.provider_combo.addItem("OpenRouter · GLM (nube)", "openrouter")
        self.provider_combo.addItem("Local · Qwen (offline)", "local")
        self.provider_combo.setCurrentIndex(max(0, self.provider_combo.findData(get_setting("llm_cleanup_provider", "groq"))))
        al.addWidget(self.provider_combo)

        self.context = Switch("Adaptar tono según la app activa (Slack casual, Gmail formal…)")
        self.context.setChecked(get_setting("context_aware_tone", True))
        al.addWidget(self.context)

        xl = group("Texto", gen)
        self.commands = Switch("Comandos de voz (\"nueva línea\", \"punto y aparte\", \"coma\")")
        self.commands.setChecked(get_setting("smart_commands_enabled", True))
        xl.addWidget(self.commands)
        self.dict_toggle = Switch("Usar diccionario personal como vocabulario")
        self.dict_toggle.setChecked(get_setting("personal_dictionary_enabled", True))
        xl.addWidget(self.dict_toggle)
        self.subs_toggle = Switch("Sustituciones de texto (btw → by the way)")
        self.subs_toggle.setChecked(get_setting("text_substitutions_enabled", True))
        xl.addWidget(self.subs_toggle)

        # ============ SYSTEM ============
        ap = group("Apariencia", sysl)
        ap.addWidget(dim("Tema"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Automático — sigue el sistema", "auto")
        self.theme_combo.addItem("Claro", "light")
        self.theme_combo.addItem("Oscuro", "dark")
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(get_setting("theme", "auto"))))
        ap.addWidget(self.theme_combo)

        pl = group("Inserción de texto", sysl)
        pl.addWidget(dim("Método de pegado"))
        self.paste_combo = QComboBox()
        self.paste_combo.addItem("Keystroke — no toca tu portapapeles (recomendado)", "keystroke")
        self.paste_combo.addItem("Clipboard + Cmd+V — sobrescribe el portapapeles", "clipboard")
        self.paste_combo.setCurrentIndex(0 if get_setting("paste_backend", "keystroke") == "keystroke" else 1)
        pl.addWidget(self.paste_combo)
        self.streaming = Switch("Streaming paste (typing palabra-por-palabra)")
        self.streaming.setChecked(get_setting("streaming_paste_enabled", False))
        pl.addWidget(self.streaming)

        snd = group("Sonido", sysl)
        self.sound_start = Switch("Sonido al empezar a dictar")
        self.sound_start.setChecked(get_setting("sound_on_start", False))
        snd.addWidget(self.sound_start)
        self.sound_done = Switch("Sonido al terminar")
        self.sound_done.setChecked(get_setting("sound_on_done", False))
        snd.addWidget(self.sound_done)

        bl = group("Comportamiento", sysl)
        self.command_mode = Switch("Command Mode (Ctrl+Shift hold → transforma selección con voz · el audio se transcribe local; la transformación usa el proveedor de limpieza configurado)")
        self.command_mode.setChecked(get_setting("command_mode_enabled", False))
        bl.addWidget(self.command_mode)
        self.save_audio = Switch("Guardar audio para re-transcribir (historial)")
        self.save_audio.setChecked(get_setting("save_audio_for_retry", True))
        bl.addWidget(self.save_audio)
        self.glass = Switch("Liquid Glass en la pill (experimental — macOS 26+)")
        self.glass.setChecked(get_setting("liquid_glass_enabled", False))
        bl.addWidget(self.glass)

        hl = group("Hotkey de mouse (opcional)", sysl)
        self.mouse = QComboBox()
        self.mouse.addItem("Ninguno", "")
        self.mouse.addItem("Click medio (rueda)", "middle")
        self.mouse.addItem("Botón lateral 1 (Mouse4)", "x1")
        self.mouse.addItem("Botón lateral 2 (Mouse5)", "x2")
        self.mouse.setCurrentIndex(max(0, self.mouse.findData(get_setting("mouse_button_hotkey") or "")))
        hl.addWidget(self.mouse)

        kl = group("API Keys · macOS Keychain", sysl)
        kl.addWidget(dim("Groq API Key (STT en la nube + limpieza Llama)"))
        self.groq_key = QLineEdit(); self.groq_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.groq_key.setPlaceholderText(self._key_status("GROQ_API_KEY"))
        kl.addWidget(self.groq_key)
        kl.addWidget(dim("OpenRouter API Key (limpieza GLM)"))
        self.or_key = QLineEdit(); self.or_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.or_key.setPlaceholderText(self._key_status("OPENROUTER_API_KEY"))
        kl.addWidget(self.or_key)
        kl.addWidget(dim("Se guardan en el Keychain de macOS. Deja en blanco para conservar la actual."))

        # Save bar
        bar = QHBoxLayout()
        bar.addStretch()

        relaunch_btn = secondary_button("Reiniciar SFlow")
        relaunch_btn.clicked.connect(self._relaunch)
        bar.addWidget(relaunch_btn)

        save = primary_button(tr("settings.save"))
        save.clicked.connect(self._save)
        bar.addWidget(save)
        root.addLayout(bar)

        # Snapshot of relaunch-sensitive settings — used by _save() to decide
        # whether to offer an immediate restart.
        self._snapshot = self._restart_snapshot()

        self.setLayout(root)

    @staticmethod
    def _key_status(name: str) -> str:
        """Placeholder text reflecting where the key lives — never the value."""
        return {
            "keychain": "•••••••• (guardada en Keychain)",
            "env": "•••••••• (desde .env)",
            "none": "no configurada",
        }[key_source(name)]

    def _restart_snapshot(self) -> tuple:
        """Settings that only take effect after restart. If any change → offer relaunch.

        `command_mode_enabled` is NOT here: the hotkey listener reads it live on
        every keypress, so it applies the moment it's saved. Listing it would
        promise a restart the setting doesn't need.
        """
        return (
            get_setting("mouse_button_hotkey"),
            get_setting("liquid_glass_enabled", False),
            get_setting("stt_model", "whisper-turbo-local"),
        )

    def _apply_theme_live(self):
        """Re-apply the global stylesheet for the chosen theme immediately.
        Globally-styled surfaces (dialogs, menus, message boxes) and any window
        opened afterward reflect it at once; the Hub's inline-styled content
        fully re-skins on next open/restart."""
        from PyQt6.QtWidgets import QApplication
        from ui import theme as _theme, icons as _icons
        app = QApplication.instance()
        if app is None:
            return
        scheme = _theme.resolve_scheme(get_setting("theme", "auto"))
        _theme.set_active_scheme(scheme)
        _icons.clear_cache()
        app.setStyleSheet(_theme.qss(scheme))

    def _relaunch(self):
        confirm = QMessageBox.question(
            self, "Reiniciar SFlow",
            "Se cerrará y abrirá una nueva instancia. ¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            relaunch_app()

    def _model_manager(self) -> ModelManager:
        if getattr(self, "_mm", None) is None:
            self._mm = ModelManager()
        return self._mm

    def _selected_model(self) -> dict:
        return _STT_BY_ID.get(self.model_combo.currentData(), {})

    def _refresh_model_dl(self):
        """Show the Descargar button + status only for a local model whose weights
        aren't present. Cloud (Groq) and the bundled Parakeet never show it."""
        model = self._selected_model()
        code = missing_code_for_selection(model, self._model_manager())
        missing = code is not None
        self.model_dl_btn.setVisible(missing)
        if missing:
            self.model_dl_status.setText(tr("settings.model_missing"))
        elif model.get("local"):
            self.model_dl_status.setText(tr("settings.model_ready"))
        else:
            self.model_dl_status.setText("")

    def _download_selected_model(self):
        model = self._selected_model()
        repo = model.get("model")
        if not repo:
            return
        from ui.model_download import ModelDownloadDialog
        dlg = ModelDownloadDialog(repo, self._model_manager(), self)
        dlg.exec()
        self._refresh_model_dl()

    def _save(self):
        # Capture before we overwrite: a theme or language change needs a full
        # page rebuild (inline-styled pages freeze C.*/tr() at construction).
        _old_theme = get_setting("theme", "auto")
        _old_lang = get_setting("language", "auto")
        # Honest gate: activating a local model whose weights aren't downloaded
        # surfaces CODE_MODEL_MISSING (download it), NEVER a key error — the key
        # has nothing to do with an on-device model.
        code = missing_code_for_selection(self._selected_model(), self._model_manager())
        if code is not None:
            toast = error_messages.message_for(code)
            QMessageBox.information(self, toast.title, toast.body)
            self._download_selected_model()
            if missing_code_for_selection(self._selected_model(), self._model_manager()) is not None:
                return  # still not downloaded — don't persist an unusable selection
        set_setting("stt_model", self.model_combo.currentData())
        set_setting("stt_language", self.lang_combo.currentData())
        set_setting("language", self.applang_combo.currentData())
        set_setting("input_device", self.mic_combo.currentData())
        set_setting("auto_cleanup_level", self.cleanup_combo.currentData())
        set_setting("llm_cleanup_provider", self.provider_combo.currentData())
        set_setting("context_aware_tone", self.context.isChecked())
        set_setting("smart_commands_enabled", self.commands.isChecked())
        set_setting("personal_dictionary_enabled", self.dict_toggle.isChecked())
        set_setting("text_substitutions_enabled", self.subs_toggle.isChecked())
        set_setting("paste_backend", self.paste_combo.currentData())
        set_setting("streaming_paste_enabled", self.streaming.isChecked())
        set_setting("sound_on_start", self.sound_start.isChecked())
        set_setting("sound_on_done", self.sound_done.isChecked())
        set_setting("command_mode_enabled", self.command_mode.isChecked())
        set_setting("save_audio_for_retry", self.save_audio.isChecked())
        set_setting("liquid_glass_enabled", self.glass.isChecked())
        set_setting("theme", self.theme_combo.currentData())
        self._apply_theme_live()
        # A theme or language change re-skins the whole Hub. Defer the rebuild so
        # _save returns first (rebuild_pages deleteLater's this very page).
        if (self.theme_combo.currentData() != _old_theme
                or self.applang_combo.currentData() != _old_lang):
            hub = self.window()
            if hasattr(hub, "rebuild_pages"):
                QTimer.singleShot(0, hub.rebuild_pages)
        mb = self.mouse.currentData()
        set_setting("mouse_button_hotkey", mb if mb else None)
        # API keys → Keychain (only when the user typed a new value)
        if self.groq_key.text().strip():
            set_key("GROQ_API_KEY", self.groq_key.text().strip())
            self.groq_key.clear(); self.groq_key.setPlaceholderText(self._key_status("GROQ_API_KEY"))
        if self.or_key.text().strip():
            set_key("OPENROUTER_API_KEY", self.or_key.text().strip())
            self.or_key.clear(); self.or_key.setPlaceholderText(self._key_status("OPENROUTER_API_KEY"))

        new_snapshot = self._restart_snapshot()
        needs_restart = new_snapshot != self._snapshot
        self._snapshot = new_snapshot

        if needs_restart:
            box = QMessageBox(self)
            box.setWindowTitle("Guardado")
            box.setText("Algunos cambios requieren reiniciar SFlow para aplicarse.")
            restart_btn = box.addButton("Reiniciar ahora", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Después", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is restart_btn:
                relaunch_app()
        else:
            QMessageBox.information(self, tr("settings.saved_title"), tr("settings.saved_body"))


class InsightsPage(QWidget):
    """Usage analytics — total words, WPM, streak, per-app breakdown, activity."""

    def __init__(self, db: TranscriptionDB):
        super().__init__()
        self.db = db
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 16)
        outer.setSpacing(16)
        title = page_title(tr("page.insights"))
        outer.addWidget(title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._body_host = QWidget()
        self.body = QVBoxLayout(self._body_host)
        self.body.setContentsMargins(0, 0, 8, 0)
        self.body.setSpacing(16)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._body_host)
        outer.addWidget(self._scroll, 1)

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                InsightsPage._clear(item.layout())

    def _stat_card(self, value: str, label: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(f"#card {{ background: {C.BG_CARD}; border: 1px solid {C.DIVIDER}; border-radius: 12px; }}")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(4)
        v = QLabel(value)
        v.setStyleSheet(f"color: {C.TEXT}; font-size: 26px; font-weight: 700;")
        lb = QLabel(label)
        lb.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px;")
        cl.addWidget(v)
        cl.addWidget(lb)
        return card

    def _section(self, name: str) -> QVBoxLayout:
        box = QFrame()
        box.setObjectName("card")
        box.setStyleSheet(f"#card {{ background: {C.BG_CARD}; border: 1px solid {C.DIVIDER}; border-radius: 12px; }}")
        inner = QVBoxLayout(box)
        inner.setContentsMargins(16, 14, 16, 14)
        inner.setSpacing(10)
        header = QLabel(name)
        header.setStyleSheet(f"color: {C.TEXT}; font-size: 14px; font-weight: 600; border: none;")
        inner.addWidget(header)
        self.body.addWidget(box)
        return inner

    def reload(self):
        self._clear(self.body)
        d = self.db.insights()

        cards = QHBoxLayout()
        cards.setSpacing(12)
        cards.addWidget(self._stat_card(f"{d['words']:,}", "Palabras totales"))
        cards.addWidget(self._stat_card(f"{round(d['wpm'])}", "Palabras / minuto"))
        cards.addWidget(self._stat_card(f"{d['count']:,}", "Dictados"))
        cards.addWidget(self._stat_card(f"{d['streak']}", "Racha (días)"))
        self.body.addLayout(cards)

        # Per-app usage bars
        sec = self._section("Uso por app")
        per_app = d["per_app"]
        if not per_app:
            empty = QLabel("Aún no hay dictados. Dicta algo con Ctrl+Alt.")
            empty.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px; border: none;")
            sec.addWidget(empty)
        else:
            maxn = max(a["n"] for a in per_app) or 1
            for a in per_app:
                row = QHBoxLayout()
                row.setSpacing(10)
                name = QLabel(a["app"])
                name.setFixedWidth(150)
                name.setStyleSheet(f"color: {C.TEXT}; font-size: 12px; border: none;")
                row.addWidget(name)
                track = QFrame()
                track.setFixedHeight(10)
                track.setStyleSheet(f"background: {C.BG_INPUT}; border-radius: 5px;")
                tl = QHBoxLayout(track)
                tl.setContentsMargins(0, 0, 0, 0)
                fill = QFrame()
                fill.setStyleSheet(f"background: {C.ACCENT}; border-radius: 5px;")
                tl.addWidget(fill, max(1, round(100 * a["n"] / maxn)))
                spacer = QFrame()
                spacer.setStyleSheet("background: transparent;")
                tl.addWidget(spacer, max(0, 100 - round(100 * a["n"] / maxn)))
                row.addWidget(track, 1)
                cnt = QLabel(str(a["n"]))
                cnt.setFixedWidth(40)
                cnt.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px; border: none;")
                cnt.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                row.addWidget(cnt)
                sec.addLayout(row)

        # Activity strip — last 21 days
        act = self._section("Actividad (últimos 21 días)")
        strip = QHBoxLayout()
        strip.setSpacing(4)
        per_day = d["per_day"]
        from datetime import date, timedelta
        today = date.today()
        vals = [per_day.get((today - timedelta(days=i)).isoformat(), 0) for i in range(20, -1, -1)]
        mx = max(vals) or 1
        for n in vals:
            sq = QFrame()
            sq.setFixedSize(13, 13)
            if n == 0:
                sq.setStyleSheet(f"background: {C.BG_INPUT}; border-radius: 3px;")
            else:
                alpha = 90 + int(165 * min(1.0, n / mx))
                sq.setStyleSheet(f"background: rgba(140,80,220,{alpha}); border-radius: 3px;")
            strip.addWidget(sq)
        strip.addStretch()
        act.addLayout(strip)


class TransformsPage(QWidget):
    """Edit the 8 Opt+1…8 rewrite prompts (were only editable via settings.json)."""

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 16)
        outer.setSpacing(12)

        title = page_title("Transforms")
        outer.addWidget(title)
        sub = QLabel("Reescrituras con IA sobre el texto seleccionado. Selecciona texto y aplica con ⌥+1…8.")
        sub.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px;")
        sub.setWordWrap(True)
        outer.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 4, 8, 4)
        il.setSpacing(10)
        il.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._rows = []
        prompts = get_setting("transform_prompts", [])
        for i in range(8):
            p = prompts[i] if i < len(prompts) else {"label": "", "prompt": ""}
            card = QFrame()
            card.setObjectName("card")
            card.setStyleSheet(f"#card {{ background: {C.BG_CARD}; border: 1px solid {C.DIVIDER}; border-radius: 10px; }}")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 12)
            cl.setSpacing(8)
            head = QHBoxLayout()
            badge = QLabel(f"⌥ {i+1}")
            badge.setStyleSheet(f"color: {C.TEXT}; background: {C.BG_INPUT}; border: 1px solid {C.DIVIDER};"
                                f" border-radius: 6px; padding: 3px 9px; font-size: 12px; font-weight: 600;")
            head.addWidget(badge)
            le = QLineEdit(p.get("label", ""))
            le.setPlaceholderText("Nombre del transform")
            head.addWidget(le, 1)
            cl.addLayout(head)
            pe = QPlainTextEdit(p.get("prompt", ""))
            pe.setPlaceholderText("Instrucción para el LLM (ej: Reescribe este texto de forma más concisa…)")
            pe.setFixedHeight(60)
            cl.addWidget(pe)
            il.addWidget(card)
            self._rows.append((le, pe))

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        bar = QHBoxLayout()
        reset = secondary_button("Restaurar predeterminados")
        reset.clicked.connect(self._reset)
        bar.addWidget(reset)
        bar.addStretch()
        save = primary_button("Guardar transforms")
        save.clicked.connect(self._save)
        bar.addWidget(save)
        outer.addLayout(bar)

    def _save(self):
        prompts = [
            {"label": le.text().strip() or f"Transform {i+1}", "prompt": pe.toPlainText().strip()}
            for i, (le, pe) in enumerate(self._rows)
        ]
        set_setting("transform_prompts", prompts)
        QMessageBox.information(self, "Guardado", "Transforms actualizados. ⌥+1…8 usan los nuevos prompts.")

    def _reset(self):
        from config import _default_settings
        defaults = _default_settings().get("transform_prompts", [])
        for i, (le, pe) in enumerate(self._rows):
            d = defaults[i] if i < len(defaults) else {"label": "", "prompt": ""}
            le.setText(d.get("label", ""))
            pe.setPlainText(d.get("prompt", ""))


class HomePage(QWidget):
    def __init__(self, db: TranscriptionDB):
        super().__init__()
        self.db = db
        root = QVBoxLayout()
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(18)

        hour = datetime.now().hour
        greet = "Buenos días" if hour < 13 else ("Buenas tardes" if hour < 20 else "Buenas noches")
        title = page_title(greet)
        root.addWidget(title)

        shortcuts = QLabel(
            "  <b>Ctrl+Alt</b> hold  ·  dictado normal<br>"
            "  <b>Ctrl+Shift</b> hold  ·  Command Mode (transforma selección)<br>"
            "  Doble-tap <b>Ctrl</b>  ·  hands-free (otra vez para parar)<br>"
            "  <b>Cmd+Shift+H</b>  ·  abre este Hub"
        )
        shortcuts.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 13px; line-height: 1.7;")
        shortcuts.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(shortcuts)

        # Stats row
        self._stats_row = QHBoxLayout()
        self._stats_row.setSpacing(10)
        root.addLayout(self._stats_row)
        self._refresh_stats()

        # Latest card
        recent_lbl = QLabel("Último dictado")
        recent_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px; margin-top: 8px;")
        root.addWidget(recent_lbl)

        self._latest_container = QWidget()
        lv = QVBoxLayout(self._latest_container)
        lv.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._latest_container)
        self._refresh_latest()

        root.addStretch()
        self.setLayout(root)

    def _stat_card(self, value: str, label: str) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        f.setStyleSheet(f"#card {{ background: {C.BG_CARD}; border: 1px solid {C.DIVIDER}; border-radius: 12px; }}")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)
        v = QLabel(value)
        v.setStyleSheet(f"color: {C.TEXT}; font-size: 26px; font-weight: 600;")
        l = QLabel(label)
        l.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 11px;")
        lay.addWidget(v)
        lay.addWidget(l)
        return f

    def _refresh_stats(self):
        while self._stats_row.count():
            item = self._stats_row.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        rows = self.db.get_recent(limit=500)
        total = len(rows)
        words = sum(len((r.get("text") or "").split()) for r in rows)
        today = 0
        today_prefix = datetime.now().strftime("%Y-%m-%d")
        for r in rows:
            ts = r.get("created_at") or ""
            if ts.startswith(today_prefix):
                today += 1
        self._stats_row.addWidget(self._stat_card(str(total), "transcripciones totales"))
        self._stats_row.addWidget(self._stat_card(str(words), "palabras dictadas"))
        self._stats_row.addWidget(self._stat_card(str(today), "hoy"))

    def _refresh_latest(self):
        lay = self._latest_container.layout()
        while lay.count():
            w = lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        rows = self.db.get_recent(limit=1)
        if not rows:
            e = QLabel("Aún no has dictado nada. Prueba Ctrl+Alt hold.")
            e.setStyleSheet(f"color: {C.TEXT_FAINT}; font-size: 13px; padding: 20px; background: {C.BG_CARD}; border-radius: 10px; border: 1px solid {C.DIVIDER};")
            lay.addWidget(e)
            return
        card = TranscriptionCard(rows[0])
        lay.addWidget(card)

    def reload(self):
        self._refresh_stats()
        self._refresh_latest()


class HubWindow(QWidget):
    def __init__(self, db: TranscriptionDB):
        super().__init__()
        self.db = db
        self.setWindowTitle("SFlow")
        self.resize(880, 620)
        # Scope the window sheet by objectName so its box props don't leak into
        # styled descendants (Qt propagates bare-selector borders to children).
        self.setObjectName("HubWindow")
        self.setStyleSheet(f"#HubWindow {{ background: {C.BG}; color: {C.TEXT}; }}")

        # --- Layout ---
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        side = QFrame()
        side.setFixedWidth(190)
        side.setObjectName("sidebar")
        side.setStyleSheet(f"#sidebar {{ background: {C.BG_ALT}; border-right: 1px solid {C.DIVIDER}; }}")
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 18, 14, 14)
        sl.setSpacing(4)

        # Logo + brand
        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)
        logo = QLabel()
        pm = QPixmap(LOGO_PATH)
        if not pm.isNull():
            logo.setPixmap(pm.scaled(22, 22, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        brand_row.addWidget(logo)
        name = QLabel("SFlow")
        name.setStyleSheet(f"color: {C.TEXT}; font-size: 15px; font-weight: 600;")
        brand_row.addWidget(name)
        brand_row.addStretch()
        w = QWidget()
        w.setLayout(brand_row)
        sl.addWidget(w)
        sl.addSpacing(18)

        self.btn_home = SidebarButton("home", tr("nav.home"))
        self.btn_insights = SidebarButton("insights", tr("nav.insights"))
        self.btn_hist = SidebarButton("history", tr("nav.history"))
        self.btn_dict = SidebarButton("dictionary", tr("nav.dictionary"))
        self.btn_snip = SidebarButton("snippets", tr("nav.snippets"))
        self.btn_trans = SidebarButton("transforms", "Transforms")
        self.btn_set = SidebarButton("settings", tr("nav.settings"))
        for b in (self.btn_home, self.btn_insights, self.btn_hist, self.btn_dict, self.btn_snip, self.btn_trans, self.btn_set):
            sl.addWidget(b)
        sl.addStretch()
        self.btn_home.setChecked(True)
        root.addWidget(side)

        # Pages
        self.pages = QStackedWidget()
        self.home_page = HomePage(db)
        self.insights_page = InsightsPage(db)
        self.history_page = HistoryPage(db)
        self.dict_page = DictionaryPage()
        self.snippets_page = SnippetsPage()
        self.transforms_page = TransformsPage()
        self.settings_page = SettingsPage()
        self.pages.addWidget(self.home_page)
        self.pages.addWidget(self.insights_page)
        self.pages.addWidget(self.history_page)
        self.pages.addWidget(self.dict_page)
        self.pages.addWidget(self.snippets_page)
        self.pages.addWidget(self.transforms_page)
        self.pages.addWidget(self.settings_page)
        root.addWidget(self.pages, 1)

        self.btn_home.clicked.connect(lambda: self._go(0))
        self.btn_insights.clicked.connect(lambda: self._go(1))
        self.btn_hist.clicked.connect(lambda: self._go(2))
        self.btn_dict.clicked.connect(lambda: self._go(3))
        self.btn_snip.clicked.connect(lambda: self._go(4))
        self.btn_trans.clicked.connect(lambda: self._go(5))
        self.btn_set.clicked.connect(lambda: self._go(6))

    def rebuild_pages(self):
        """Destroy and reconstruct every page.

        A live theme or language change can't be applied in place: each page
        freezes C.* colors and tr() strings at construction. Rebuilding is the
        only faithful re-skin. The active page and the history search text are
        preserved so the switch is invisible to the user.
        """
        idx = self.pages.currentIndex()
        search = ""
        try:
            search = self.history_page.search.text()
        except Exception:
            pass

        while self.pages.count():
            w = self.pages.widget(0)
            self.pages.removeWidget(w)
            w.deleteLater()

        self.home_page = HomePage(self.db)
        self.insights_page = InsightsPage(self.db)
        self.history_page = HistoryPage(self.db)
        self.dict_page = DictionaryPage()
        self.snippets_page = SnippetsPage()
        self.transforms_page = TransformsPage()
        self.settings_page = SettingsPage()
        for p in (self.home_page, self.insights_page, self.history_page, self.dict_page,
                  self.snippets_page, self.transforms_page, self.settings_page):
            self.pages.addWidget(p)
        self.pages.setCurrentIndex(idx)
        try:
            if search:
                self.history_page.search.setText(search)
        except Exception:
            pass

    def _go(self, idx: int):
        self.pages.setCurrentIndex(idx)
        if idx == 0:
            self.home_page.reload()
        elif idx == 1:
            self.insights_page.reload()
        elif idx == 2:
            self.history_page.reload()
        elif idx == 4:
            self.snippets_page.reload()

    def showEvent(self, event):
        super().showEvent(event)
        self.home_page.reload()
        self.history_page.reload()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
