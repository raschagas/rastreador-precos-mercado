"""Data-directory resolution.

Truly portable: data lives in ``<app_folder>/data/`` whenever that folder is
writable (so moving/copying the whole folder carries the DB + settings along).
Falls back to ``%APPDATA%\\RastreadorPrecos`` (or ``~/.local/share`` off-Windows)
when the app folder is read-only (e.g. installed under Program Files).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "RastreadorPrecos"


def _app_root() -> Path:
    """Folder that holds the app. For a frozen/portable layout this is where
    the launcher lives; in dev it's the repo root (parent of ``app/``)."""
    if getattr(sys, "frozen", False):  # PyInstaller, just in case
        return Path(sys.executable).resolve().parent
    # engine/paths.py -> engine -> app -> repo root
    return Path(__file__).resolve().parents[2]


def _is_writable(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def _resolve_data_dir() -> Path:
    portable = _app_root() / "data"
    if _is_writable(portable):
        return portable
    # Fallback: per-user app data
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    fallback = base / APP_NAME
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


DATA_DIR = _resolve_data_dir()
DB_PATH = str(DATA_DIR / "prices.db")
PRODUCTS_FILE = str(DATA_DIR / "products.json")
SETTINGS_FILE = str(DATA_DIR / "settings.json")
LOG_FILE = str(DATA_DIR / "app.log")
