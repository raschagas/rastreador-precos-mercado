"""Rastreador de Preços de Mercado — PySide6 desktop entrypoint."""
from __future__ import annotations

import logging
import os
import sys

# Ensure this app/ directory is importable (engine, gui) regardless of how the
# bundled/embeddable interpreter configures sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication

from engine import paths
from engine.database import init_db
from gui.main_window import MainWindow


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(paths.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> int:
    _setup_logging()
    init_db()
    app = QApplication(sys.argv)
    app.setApplicationName("Rastreador de Preços")
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
