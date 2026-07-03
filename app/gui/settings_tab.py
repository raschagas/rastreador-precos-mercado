"""Tab 3 — persistent settings: Telegram, CEP, schedule, notification toggles."""
from __future__ import annotations

import asyncio

from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from engine import config, notify


class SettingsTab(QWidget):
    def __init__(self, on_saved=None):
        super().__init__()
        self._on_saved = on_saved

        # — Telegram / regional —
        self.token = QLineEdit(); self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("123456:ABC-... (opcional)")
        self.chat_id = QLineEdit(); self.chat_id.setPlaceholderText("ex.: 123456789")
        self.cep = QLineEdit(); self.cep.setPlaceholderText("ex.: 71687206 (seu CEP no DF)")
        tg_box = QGroupBox("Telegram e região")
        tgf = QFormLayout(tg_box)
        tgf.addRow("Bot token", self.token)
        tgf.addRow("Chat ID", self.chat_id)
        tgf.addRow("CEP (Brasília/DF)", self.cep)

        # — Schedule —
        self.interval = QSpinBox(); self.interval.setRange(1, 168); self.interval.setSuffix(" h")
        sch_box = QGroupBox("Agendamento")
        schf = QFormLayout(sch_box)
        schf.addRow("Intervalo de varredura", self.interval)

        # — Notifications —
        self.notif_on = QCheckBox("Ativar notificações")
        self.telegram_on = QCheckBox("Enviar via Telegram")
        self.toast_on = QCheckBox("Mostrar toast do Windows")
        self.new_lows = QCheckBox("Notificar novas mínimas (R$/kg)")
        self.drops = QCheckBox("Notificar quedas de preço")
        self.notif_on.toggled.connect(self._sync_notif_enabled)
        nbox = QGroupBox("Notificações")
        nl = QVBoxLayout(nbox)
        for w in (self.notif_on, self.telegram_on, self.toast_on, self.new_lows, self.drops):
            nl.addWidget(w)
        test_btn = QPushButton("Enviar notificação de teste")
        test_btn.clicked.connect(self._test)
        nl.addWidget(test_btn)

        # — Scraping knobs —
        self.max_pages = QSpinBox(); self.max_pages.setRange(1, 50)
        self.concurrency = QSpinBox(); self.concurrency.setRange(1, 16)
        self.batch_delay = QSpinBox(); self.batch_delay.setRange(0, 300); self.batch_delay.setSuffix(" s")
        adv_box = QGroupBox("Avançado (scraping)")
        advf = QFormLayout(adv_box)
        advf.addRow("Máx. páginas por loja", self.max_pages)
        advf.addRow("Scrapers simultâneos", self.concurrency)
        advf.addRow("Atraso entre lotes", self.batch_delay)

        save_btn = QPushButton("💾 Salvar configurações")
        save_btn.clicked.connect(self._save)
        save_row = QHBoxLayout(); save_row.addStretch(1); save_row.addWidget(save_btn)

        root = QVBoxLayout(self)
        root.addWidget(tg_box)
        root.addWidget(sch_box)
        root.addWidget(nbox)
        root.addWidget(adv_box)
        note = QLabel("As configurações são salvas na pasta de dados do programa e "
                      "persistem entre execuções.")
        note.setWordWrap(True)
        root.addWidget(note)
        root.addLayout(save_row)
        root.addStretch(1)

        self.load()

    # ── load / save ───────────────────────────────────────────────────────────
    def load(self) -> None:
        s = config.load_settings()
        self.token.setText(str(s.get("telegram_token", "")))
        self.chat_id.setText(str(s.get("telegram_chat_id", "")))
        self.cep.setText(str(s.get("brasilia_cep", "")))
        self.interval.setValue(int(s.get("scan_interval_hours", 6)))
        self.notif_on.setChecked(bool(s.get("notifications_enabled", True)))
        self.telegram_on.setChecked(bool(s.get("telegram_enabled", True)))
        self.toast_on.setChecked(bool(s.get("toast_enabled", True)))
        self.new_lows.setChecked(bool(s.get("notify_new_lows", True)))
        self.drops.setChecked(bool(s.get("notify_drops", True)))
        self.max_pages.setValue(int(s.get("max_pages", 10)))
        self.concurrency.setValue(int(s.get("max_concurrent_scrapers", 3)))
        self.batch_delay.setValue(int(s.get("product_batch_delay", 15)))
        self._sync_notif_enabled(self.notif_on.isChecked())

    def _sync_notif_enabled(self, on: bool) -> None:
        for w in (self.telegram_on, self.toast_on, self.new_lows, self.drops):
            w.setEnabled(on)

    def _collect(self) -> dict:
        return {
            "telegram_token": self.token.text().strip(),
            "telegram_chat_id": self.chat_id.text().strip(),
            "brasilia_cep": self.cep.text().strip(),
            "scan_interval_hours": self.interval.value(),
            "notifications_enabled": self.notif_on.isChecked(),
            "telegram_enabled": self.telegram_on.isChecked(),
            "toast_enabled": self.toast_on.isChecked(),
            "notify_new_lows": self.new_lows.isChecked(),
            "notify_drops": self.drops.isChecked(),
            "max_pages": self.max_pages.value(),
            "max_concurrent_scrapers": self.concurrency.value(),
            "product_batch_delay": self.batch_delay.value(),
        }

    def _save(self) -> None:
        config.save_settings(self._collect())
        QMessageBox.information(self, "Configurações", "Configurações salvas.")
        if self._on_saved:
            self._on_saved()

    def _test(self) -> None:
        # Save first so the test uses the on-screen values.
        config.save_settings(self._collect())
        try:
            status = asyncio.run(notify.send_test(config.load_settings()))
        except Exception as e:
            status = f"Erro: {e}"
        QMessageBox.information(self, "Teste de notificação", status)
