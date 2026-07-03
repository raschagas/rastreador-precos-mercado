"""Tab 1 — tracked items with current/lowest R$/kg + dates, and CRUD buttons."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QMessageBox, QPushButton,
    QTableWidget, QVBoxLayout, QWidget,
)

from engine import products
from engine.database import get_db, get_item_summary, get_lowest_ever_ppk
from .fmt import brl_kg, short_date, site_name
from .item_dialog import ItemDialog
from .table import cell

COLS = ["Item", "Menor R$/kg atual", "Loja mais barata", "Menor histórico",
        "Visto em", "Ofertas"]


class ItemsTab(QWidget):
    def __init__(self, on_change=None):
        super().__init__()
        self._on_change = on_change  # callback to refresh siblings/status

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self._edit)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(COLS)):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)

        add_btn = QPushButton("➕ Adicionar")
        edit_btn = QPushButton("✏️ Editar")
        del_btn = QPushButton("🗑️ Remover")
        add_btn.clicked.connect(self._add)
        edit_btn.clicked.connect(self._edit)
        del_btn.clicked.connect(self._remove)

        bar = QHBoxLayout()
        bar.addWidget(add_btn)
        bar.addWidget(edit_btn)
        bar.addWidget(del_btn)
        bar.addStretch(1)

        root = QVBoxLayout(self)
        root.addLayout(bar)
        root.addWidget(self.table)

    # ── data ────────────────────────────────────────────────────────────────
    def refresh(self) -> None:
        items = products.list_items()
        summary = {}
        lowest = {}
        db = get_db()
        try:
            for row in get_item_summary(db):
                summary[row["model_family"]] = row
            for it in items:
                lo = get_lowest_ever_ppk(db, it.get("name"))
                if lo:
                    lowest[it["name"]] = lo
        finally:
            db.close()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(items))
        for r, it in enumerate(items):
            name = it.get("name", "")
            s = summary.get(name, {})
            lo = lowest.get(name, {})
            cur_ppk = s.get("current_ppk")
            self._set(r, 0, name)
            self._set(r, 1, brl_kg(cur_ppk), sort=cur_ppk)
            self._set(r, 2, site_name(s.get("cheapest_site")) if s.get("cheapest_site") else "—")
            self._set(r, 3, brl_kg(lo.get("ppk")), sort=lo.get("ppk"))
            self._set(r, 4, short_date(lo.get("seen_at")))
            self._set(r, 5, str(s.get("n_offers", 0)), sort=s.get("n_offers", 0))
        self.table.setSortingEnabled(True)

    def _set(self, r, c, text, sort=None):
        self.table.setItem(r, c, cell(text, sort=sort))

    def _selected_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        cell = self.table.item(row, 0)
        return cell.text() if cell else None

    # ── actions ──────────────────────────────────────────────────────────────
    def _add(self):
        dlg = ItemDialog(self, save_fn=products.add_item)
        if dlg.exec():
            self._changed()

    def _edit(self, *_):
        name = self._selected_name()
        if not name:
            QMessageBox.information(self, "Editar", "Selecione um item na tabela.")
            return
        current = products.get_item(name)
        dlg = ItemDialog(self, item=current,
                         save_fn=lambda data: products.edit_item(name, data))
        if dlg.exec():
            self._changed()

    def _remove(self):
        name = self._selected_name()
        if not name:
            QMessageBox.information(self, "Remover", "Selecione um item na tabela.")
            return
        if QMessageBox.question(self, "Remover item",
                                f"Remover “{name}” do rastreamento?") == QMessageBox.Yes:
            products.remove_item(name)
            self._changed()

    def _changed(self):
        self.refresh()
        if self._on_change:
            self._on_change()
