"""Cancelable model-download UI.

The offline promise breaks the moment a 1.6GB fetch happens invisibly inside the
pill's PROCESSING state. This gives the download a face: a progress bar the user
starts on purpose and can cancel, driven by core.models.ModelManager.

``ModelDownloadWorker`` is deliberately Qt-signal-only and free of widgets, so
its download/cancel logic is unit-testable by driving ``run()`` synchronously
with a mocked ModelManager.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout,
)

from core.models import DownloadCancelled, ModelManager, catalog_entry
from core.i18n import tr
from ui import theme
from ui.components import ghost_button, primary_button


class ModelDownloadWorker(QObject):
    """Runs one ModelManager.download in a worker thread, reporting progress and
    honouring a cancel flag."""

    progress = pyqtSignal(float)   # 0.0 .. 1.0
    finished = pyqtSignal(str)     # local snapshot path
    failed = pyqtSignal(str)       # error text
    cancelled = pyqtSignal()

    def __init__(self, repo_id: str, manager: ModelManager | None = None):
        super().__init__()
        self._repo_id = repo_id
        self._manager = manager or ModelManager()
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            path = self._manager.download(
                self._repo_id,
                progress_cb=lambda f: self.progress.emit(float(f)),
                should_cancel=lambda: self._cancel,
            )
            self.finished.emit(path or "")
        except DownloadCancelled:
            self.cancelled.emit()
        except Exception as e:  # network, disk, HF error — report, never crash
            self.failed.emit(str(e))


class ModelDownloadDialog(QDialog):
    """A modal progress dialog. Downloads on a QThread so the UI stays responsive
    and Cancel actually interrupts."""

    def __init__(self, repo_id: str, manager: ModelManager | None = None, parent=None):
        super().__init__(parent)
        self._repo_id = repo_id
        self.result_path: str | None = None
        entry = catalog_entry(repo_id)
        size = entry.get("size_mb", 0)

        self.setWindowTitle(tr("download.title"))
        self.setModal(True)
        self.setFixedWidth(420)
        t = theme.tokens(theme.active_scheme())

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(14)

        title = QLabel(entry.get("label", repo_id))
        title.setStyleSheet(f"color: {t['text']}; font-size: 15px; font-weight: 600;")
        root.addWidget(title)

        sub = QLabel(tr("download.subtitle", size=size))
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {t['text_dim']}; font-size: 12px;")
        root.addWidget(sub)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        root.addWidget(self.bar)

        self.status = QLabel(tr("download.preparing"))
        self.status.setStyleSheet(f"color: {t['text_dim']}; font-size: 12px;")
        root.addWidget(self.status)

        bar = QHBoxLayout()
        bar.addStretch()
        self._cancel_btn = ghost_button(tr("download.cancel"))
        self._cancel_btn.clicked.connect(self._on_cancel)
        bar.addWidget(self._cancel_btn)
        self._close_btn = primary_button(tr("download.done_btn"))
        self._close_btn.setVisible(False)
        self._close_btn.clicked.connect(self.accept)
        bar.addWidget(self._close_btn)
        root.addLayout(bar)

        self._thread = QThread(self)
        self._worker = ModelDownloadWorker(repo_id, manager)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress, Qt.ConnectionType.QueuedConnection)
        self._worker.finished.connect(self._on_finished, Qt.ConnectionType.QueuedConnection)
        self._worker.failed.connect(self._on_failed, Qt.ConnectionType.QueuedConnection)
        self._worker.cancelled.connect(self._on_cancelled, Qt.ConnectionType.QueuedConnection)
        self._thread.start()

    def _on_progress(self, frac: float):
        pct = int(frac * 100)
        self.bar.setValue(pct)
        self.status.setText(tr("download.progress", pct=pct))

    def _finish_thread(self):
        try:
            self._thread.quit()
            self._thread.wait(2000)
        except Exception:
            pass

    def _on_finished(self, path: str):
        self.result_path = path
        self.bar.setValue(100)
        self.status.setText(tr("download.complete"))
        self._cancel_btn.setVisible(False)
        self._close_btn.setVisible(True)
        self._finish_thread()

    def _on_failed(self, _msg: str):
        self.status.setText(tr("download.failed"))
        self._cancel_btn.setText(tr("download.cancel"))
        self._finish_thread()

    def _on_cancelled(self):
        self._finish_thread()
        self.reject()

    def _on_cancel(self):
        self.status.setText(tr("download.cancelling"))
        self._worker.cancel()

    def closeEvent(self, event):  # noqa: N802 - Qt
        self._worker.cancel()
        self._finish_thread()
        super().closeEvent(event)
