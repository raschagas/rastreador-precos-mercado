"""Main window — tabs, status header, manual scan button, and the interval
scheduler that drives background scans."""
from __future__ import annotations

import logging
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QProgressBar, QPushButton, QTabWidget,
    QVBoxLayout, QWidget,
)

from engine import config, products
from engine.database import get_db, get_status
from .fmt import short_date
from .items_tab import ItemsTab
from .listings_tab import ListingsTab
from .scan_worker import ScanWorker
from .settings_tab import SettingsTab

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rastreador de Preços de Mercado")
        self.resize(980, 680)
        self._worker: ScanWorker | None = None
        self._next_scan_epoch: float | None = None

        # — header —
        self.status_lbl = QLabel("—")
        self.next_lbl = QLabel("")
        self.scan_btn = QPushButton("🔍 Escanear agora")
        self.scan_btn.clicked.connect(self.start_scan)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(160)

        header = QHBoxLayout()
        header.addWidget(self.status_lbl, 1)
        header.addWidget(self.progress)
        header.addWidget(self.next_lbl)
        header.addWidget(self.scan_btn)

        # — tabs —
        self.tabs = QTabWidget()
        self.items_tab = ItemsTab(on_change=self._on_items_changed)
        self.listings_tab = ListingsTab()
        self.settings_tab = SettingsTab(on_saved=self._on_settings_saved)
        self.tabs.addTab(self.items_tab, "📋 Itens rastreados")
        self.tabs.addTab(self.listings_tab, "🏷️ Ofertas")
        self.tabs.addTab(self.settings_tab, "⚙️ Configurações")

        central = QWidget()
        root = QVBoxLayout(central)
        root.addLayout(header)
        root.addWidget(self.tabs)
        self.setCentralWidget(central)

        # — timers —
        self.scan_timer = QTimer(self)
        self.scan_timer.setSingleShot(True)
        self.scan_timer.timeout.connect(self._scheduled_scan)
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._tick)
        self.ui_timer.start(1000)

        self.refresh_all()
        self._reschedule()

    # ── refresh ──────────────────────────────────────────────────────────────
    def refresh_all(self) -> None:
        self.items_tab.refresh()
        self.listings_tab.refresh()
        self._update_status()

    def _update_status(self) -> None:
        db = get_db()
        try:
            st = get_status(db)
        finally:
            db.close()
        n_items = len(products.list_items())
        self.status_lbl.setText(
            f"Itens rastreados: {n_items}  ·  Ofertas ativas: {st['products_active']}  ·  "
            f"Última varredura: {short_date(st['last_scan'])}"
        )

    def _on_items_changed(self) -> None:
        self.listings_tab.refresh()
        self._update_status()

    def _on_settings_saved(self) -> None:
        self._reschedule()
        self._update_status()

    # ── scheduling ───────────────────────────────────────────────────────────
    def _reschedule(self) -> None:
        s = config.load_settings()
        hours = max(1, int(s.get("scan_interval_hours", 6)))
        ms = hours * 3600 * 1000
        self.scan_timer.start(ms)
        self._next_scan_epoch = time.time() + ms / 1000
        self._tick()

    def _scheduled_scan(self) -> None:
        self.start_scan()  # _reschedule happens when the scan finishes

    def _tick(self) -> None:
        if self._next_scan_epoch and not (self._worker and self._worker.isRunning()):
            remaining = int(max(0, self._next_scan_epoch - time.time()))
            h, rem = divmod(remaining, 3600)
            m, sec = divmod(rem, 60)
            self.next_lbl.setText(f"Próxima: {h:02d}:{m:02d}:{sec:02d}")

    # ── scan ─────────────────────────────────────────────────────────────────
    def start_scan(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("⏳ Escaneando…")
        self.progress.setVisible(True)
        self.next_lbl.setText("Escaneando…")
        self._worker = ScanWorker()
        self._worker.finished_ok.connect(self._scan_done)
        self._worker.failed.connect(self._scan_failed)
        self._worker.start()

    def _scan_done(self, result, sent: int) -> None:
        self._end_scan()
        msg = (f"Varredura concluída — {result.total_found} ofertas, "
               f"{len(result.new)} novas, {len(result.drops)} quedas, "
               f"{len(result.new_lows)} mínimas · {sent} notificações")
        if result.errors:
            msg += f" · ⚠️ {len(result.errors)} erros"
        self.statusBar().showMessage(msg, 15000)
        self.refresh_all()

    def _scan_failed(self, err: str) -> None:
        self._end_scan()
        self.statusBar().showMessage(f"Falha na varredura: {err}", 15000)

    def _end_scan(self) -> None:
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("🔍 Escanear agora")
        self.progress.setVisible(False)
        self._reschedule()
