"""Add/Edit dialog for a tracked item, including the exclusion-text field."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QLabel, QLineEdit, QMessageBox, QVBoxLayout,
)


def _join(v) -> str:
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v or "")


class ItemDialog(QDialog):
    """Form for one product. ``save_fn(data)`` persists it (raises ValueError on
    bad input); the dialog stays open and shows the message on error."""

    def __init__(self, parent=None, item: dict | None = None, save_fn=None):
        super().__init__(parent)
        self._save_fn = save_fn
        self._editing = item is not None
        self.setWindowTitle("Editar item" if self._editing else "Adicionar item")
        self.setMinimumWidth(520)

        item = item or {}
        form = QFormLayout()

        self.name = QLineEdit(item.get("name", ""))
        self.name.setPlaceholderText("Ex.: Bacalhau (lombo/posta)")
        form.addRow("Nome *", self.name)

        self.sams = QLineEdit(_join(item.get("search_samsclub")))
        self.sams.setPlaceholderText("termos separados por vírgula, ex.: bacalhau")
        form.addRow("Sam's Club (busca)", self.sams)

        self.swift = QLineEdit(_join(item.get("swift_categories")))
        self.swift.setPlaceholderText("categorias, ex.: pescados/bacalhau, bovinos/patinho")
        form.addRow("Swift (categorias)", self.swift)

        self.sadega = QLineEdit(_join(item.get("search_superadega")))
        self.sadega.setPlaceholderText("termos separados por vírgula, ex.: bacalhau")
        form.addRow("Superadega (busca)", self.sadega)

        self.valid = QLineEdit(item.get("valid_pattern", ""))
        self.valid.setPlaceholderText("regex que o título DEVE conter, ex.: bacalhau|saithe")
        form.addRow("Padrão válido (regex)", self.valid)

        self.exclude = QLineEdit(item.get("exclude_pattern", ""))
        self.exclude.setPlaceholderText("regex a EXCLUIR, ex.: desfiad|bolinho|croquete")
        form.addRow("Texto de exclusão (regex)", self.exclude)

        self.condition = QComboBox()
        self.condition.addItems(["novo", "usado"])
        self.condition.setCurrentText(item.get("condition", "novo"))
        form.addRow("Condição", self.condition)

        self.require_kg = QCheckBox("Exigir R$/kg (descartar itens sem peso)")
        self.require_kg.setChecked(bool(item.get("require_kg", False)))
        form.addRow("", self.require_kg)

        self.notify_new = QCheckBox("Notificar novos anúncios")
        self.notify_new.setChecked(bool(item.get("notify_new", True)))
        form.addRow("", self.notify_new)

        self.min_price = QDoubleSpinBox()
        self.min_price.setRange(0, 1_000_000); self.min_price.setPrefix("R$ ")
        self.min_price.setValue(float(item.get("min_price", 0) or 0))
        form.addRow("Preço mínimo (0 = sem)", self.min_price)

        self.max_price = QDoubleSpinBox()
        self.max_price.setRange(0, 1_000_000); self.max_price.setPrefix("R$ ")
        self.max_price.setValue(float(item.get("max_price", 0) or 0))
        form.addRow("Preço máximo (0 = sem)", self.max_price)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Salvar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        hint = QLabel("Preencha ao menos uma das buscas de loja. Os campos de "
                      "regex são opcionais mas recomendados para filtrar ruído.")
        hint.setWordWrap(True)
        root.addLayout(form)
        root.addWidget(hint)
        root.addWidget(buttons)

    def data(self) -> dict:
        return {
            "name": self.name.text().strip(),
            "search_samsclub": self.sams.text(),
            "swift_categories": self.swift.text(),
            "search_superadega": self.sadega.text(),
            "valid_pattern": self.valid.text().strip(),
            "exclude_pattern": self.exclude.text().strip(),
            "condition": self.condition.currentText(),
            "require_kg": self.require_kg.isChecked(),
            "notify_new": self.notify_new.isChecked(),
            "min_price": self.min_price.value(),
            "max_price": self.max_price.value(),
        }

    def _on_save(self) -> None:
        try:
            if self._save_fn:
                self._save_fn(self.data())
            self.accept()
        except (ValueError, KeyError) as e:
            QMessageBox.warning(self, "Não foi possível salvar", str(e))
