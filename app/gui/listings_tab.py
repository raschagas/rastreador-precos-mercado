"""Tab 2 — all offers, filterable, with a price-history chart per selection."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCharts import (QChart, QChartView, QDateTimeAxis, QLineSeries,
                              QValueAxis)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QSplitter, QTableWidget, QVBoxLayout, QWidget,
)

from engine import products
from engine.database import get_db, get_history, get_listings
from .fmt import brl, brl_kg, short_date, site_name
from .table import cell

COLS = ["Loja", "Item", "Título", "Preço pacote", "R$/kg", "Visto em", "Última vez"]
SITES = [("Todas", None), ("Sam's Club", "samsclub"), ("Swift", "swift"),
         ("Superadega", "superadega")]


class ListingsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.item_filter = QComboBox()
        self.site_filter = QComboBox()
        for label, _ in SITES:
            self.site_filter.addItem(label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("filtrar por título…")
        self.item_filter.currentIndexChanged.connect(self.refresh)
        self.site_filter.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Item:"))
        bar.addWidget(self.item_filter)
        bar.addWidget(QLabel("Loja:"))
        bar.addWidget(self.site_filter)
        bar.addWidget(self.search, 1)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._draw_history)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        for c in (0, 1, 3, 4, 5, 6):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)

        self.chart = QChart()
        self.chart.setTitle("Selecione uma oferta para ver o histórico de preço")
        self.chart.legend().hide()
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_view.setMinimumHeight(200)

        split = QSplitter(Qt.Vertical)
        top = QWidget(); tl = QVBoxLayout(top); tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.table)
        split.addWidget(top)
        split.addWidget(self.chart_view)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        root = QVBoxLayout(self)
        root.addLayout(bar)
        root.addWidget(split)

    def refresh(self) -> None:
        # keep item filter options in sync with tracked items
        current = self.item_filter.currentText()
        names = [it.get("name", "") for it in products.list_items()]
        want = ["Todos"] + names
        if [self.item_filter.itemText(i) for i in range(self.item_filter.count())] != want:
            self.item_filter.blockSignals(True)
            self.item_filter.clear(); self.item_filter.addItems(want)
            idx = self.item_filter.findText(current)
            self.item_filter.setCurrentIndex(idx if idx >= 0 else 0)
            self.item_filter.blockSignals(False)

        model_family = None
        if self.item_filter.currentIndex() > 0:
            model_family = self.item_filter.currentText()
        site = SITES[self.site_filter.currentIndex()][1]
        q = self.search.text().strip() or None

        db = get_db()
        try:
            rows = get_listings(db, model_family=model_family, site=site, q=q, limit=2000)
        finally:
            db.close()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self._set(r, 0, site_name(row["site"]))
            self._set(r, 1, row.get("model_family") or "—")
            self._set(r, 2, row.get("title", ""), pid=row["id"])
            self._set(r, 3, brl(row.get("price")), sort=row.get("price"))
            self._set(r, 4, brl_kg(row.get("price_per_kg")), sort=row.get("price_per_kg"))
            self._set(r, 5, short_date(row.get("first_seen")))
            self._set(r, 6, short_date(row.get("last_seen")))
        self.table.setSortingEnabled(True)

    def _set(self, r, c, text, sort=None, pid=None):
        self.table.setItem(r, c, cell(text, sort=sort, user=pid))

    def _draw_history(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        title_cell = self.table.item(row, 2)
        if not title_cell:
            return
        pid = title_cell.data(Qt.UserRole + 1)
        if pid is None:
            return
        db = get_db()
        try:
            hist = get_history(db, int(pid), days=180)
        finally:
            db.close()

        self.chart.removeAllSeries()
        for ax in list(self.chart.axes()):
            self.chart.removeAxis(ax)

        title = title_cell.text()[:60]
        if len(hist) < 1:
            self.chart.setTitle(f"Sem histórico ainda — {title}")
            return

        series = QLineSeries()
        ys = []
        for h in hist:
            try:
                dt = datetime.fromisoformat(h["seen_at"])
            except Exception:
                continue
            ms = int(dt.timestamp() * 1000)
            series.append(ms, float(h["price"]))
            ys.append(float(h["price"]))
        if not ys:
            self.chart.setTitle(f"Sem histórico ainda — {title}")
            return
        self.chart.addSeries(series)

        ax_x = QDateTimeAxis(); ax_x.setFormat("dd/MM"); ax_x.setTitleText("Data")
        ax_y = QValueAxis(); ax_y.setTitleText("Preço pacote (R$)")
        lo, hi = min(ys), max(ys)
        pad = max((hi - lo) * 0.1, 1.0)
        ax_y.setRange(lo - pad, hi + pad)
        self.chart.addAxis(ax_x, Qt.AlignBottom)
        self.chart.addAxis(ax_y, Qt.AlignLeft)
        series.attachAxis(ax_x)
        series.attachAxis(ax_y)
        self.chart.setTitle(f"Histórico — {title}")
