"""Shared table helpers."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem


class NumericItem(QTableWidgetItem):
    """A table cell that displays formatted text but sorts by a numeric key
    stored in ``Qt.UserRole`` (so 'R$ 93,62/kg' sorts below 'R$ 100,00/kg')."""

    def __lt__(self, other: "QTableWidgetItem") -> bool:
        a = self.data(Qt.UserRole)
        b = other.data(Qt.UserRole)
        if a is None and b is None:
            return super().__lt__(other)
        # Treat missing values as +inf so they sink to the bottom when ascending.
        a = float("inf") if a is None else a
        b = float("inf") if b is None else b
        return a < b


def cell(text, sort=None, user=None) -> QTableWidgetItem:
    """Build a read-only cell. If ``sort`` is a number, returns a NumericItem
    that sorts numerically. ``user`` stashes an extra payload (e.g. product id)."""
    if sort is not None:
        item = NumericItem(str(text))
        item.setData(Qt.UserRole, float(sort))
    else:
        item = QTableWidgetItem(str(text))
    if user is not None:
        item.setData(Qt.UserRole + 1, user)
    return item
