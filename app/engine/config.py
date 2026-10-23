"""Runtime configuration — backed by ``settings.json`` in the data dir.

The GUI's Settings tab writes ``settings.json``; the scanner calls
:func:`reload` before each run so edits take effect without a restart. Static
store parameters (hosts, Superadega store id, ibecom endpoint) are constants —
they are public catalog endpoints, not secrets. User-specific values (Telegram
token/chat id, CEP) live only in ``settings.json`` (git-ignored), never in code.
"""
from __future__ import annotations

import json
import logging
import re

from . import paths

log = logging.getLogger(__name__)

# --- Static store parameters (public endpoints) ---------------------------
SAMS_HOST = "www.samsclub.com.br"
SWIFT_HOST = "www.swift.com.br"
VTEX_PAGE_SIZE = 50  # VTEX caps _from/_to ranges at 50 items per request
SUPERADEGA_STORE_ID = "67e4246870f36a70e0746d56"  # loja "superadegapistao"
IBECOM_SEARCH_URL = "https://api.ibecom.com.br/api_ecommerce/v5/search"
SUPERADEGA_SITE_URL = "https://www.atacadistasuperadega.com.br"

# --- Defaults for user-tunable knobs (overridden by settings.json) --------
DEFAULT_SETTINGS: dict = {
    # secrets / regional
    "telegram_token": "",
    "telegram_chat_id": "-1002348762774",
    "telegram_topic_id": "4879",
    "brasilia_cep": "",          # blank by default; user enters their CEP
    # scheduling / notifications
    "scan_interval_hours": 6,
    "notifications_enabled": True,
    "telegram_enabled": True,
    "toast_enabled": True,
    "notify_new_lows": True,     # alert cheapest new R$/kg per (cut, store)
    "notify_drops": True,        # alert price drops on existing listings
    # scraping knobs
    "max_pages": 10,
    "max_concurrent_scrapers": 3,
    "product_batch_delay": 15,
    "page_delay_min": 2,
    "page_delay_max": 5,
    "query_delay_min": 10,
    "query_delay_max": 20,
    "min_price": 0.0,
    "max_price": 0.0,
    "max_notif_per_scan": 20,
}

# --- Live module-level knobs (populated by _apply, refreshed by reload) ----
MAX_PAGES = DEFAULT_SETTINGS["max_pages"]
MAX_CONCURRENT_SCRAPERS = DEFAULT_SETTINGS["max_concurrent_scrapers"]
PRODUCT_BATCH_DELAY = DEFAULT_SETTINGS["product_batch_delay"]
PAGE_DELAY_MIN = DEFAULT_SETTINGS["page_delay_min"]
PAGE_DELAY_MAX = DEFAULT_SETTINGS["page_delay_max"]
QUERY_DELAY_MIN = DEFAULT_SETTINGS["query_delay_min"]
QUERY_DELAY_MAX = DEFAULT_SETTINGS["query_delay_max"]
MIN_PRICE = DEFAULT_SETTINGS["min_price"]
MAX_PRICE = DEFAULT_SETTINGS["max_price"]
MAX_NOTIF_PER_SCAN = DEFAULT_SETTINGS["max_notif_per_scan"]
BRASILIA_CEP = ""


def load_settings() -> dict:
    """Return DEFAULT_SETTINGS overlaid with settings.json (missing file → defaults)."""
    data = {}
    try:
        with open(paths.SETTINGS_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            data = raw
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("Failed to read %s: %s — using defaults", paths.SETTINGS_FILE, e)
    merged = dict(DEFAULT_SETTINGS)
    for k, v in data.items():
        if k in merged and v is not None:
            merged[k] = v
    return merged


def save_settings(updates: dict) -> dict:
    """Merge ``updates`` into settings.json (atomic) and reload live knobs."""
    current = load_settings()
    for k, v in (updates or {}).items():
        if k in DEFAULT_SETTINGS:
            current[k] = v
    tmp = paths.SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    import os
    os.replace(tmp, paths.SETTINGS_FILE)
    reload()
    return current


def _apply(s: dict) -> None:
    """Push a settings dict into the live module-level knobs."""
    global MAX_PAGES, MAX_CONCURRENT_SCRAPERS, PRODUCT_BATCH_DELAY
    global PAGE_DELAY_MIN, PAGE_DELAY_MAX, QUERY_DELAY_MIN, QUERY_DELAY_MAX
    global MIN_PRICE, MAX_PRICE, MAX_NOTIF_PER_SCAN, BRASILIA_CEP
    MAX_PAGES = int(s["max_pages"])
    MAX_CONCURRENT_SCRAPERS = int(s["max_concurrent_scrapers"])
    PRODUCT_BATCH_DELAY = int(s["product_batch_delay"])
    PAGE_DELAY_MIN = float(s["page_delay_min"])
    PAGE_DELAY_MAX = float(s["page_delay_max"])
    QUERY_DELAY_MIN = float(s["query_delay_min"])
    QUERY_DELAY_MAX = float(s["query_delay_max"])
    MIN_PRICE = float(s["min_price"])
    MAX_PRICE = float(s["max_price"])
    MAX_NOTIF_PER_SCAN = int(s["max_notif_per_scan"])
    BRASILIA_CEP = str(s.get("brasilia_cep") or "").replace("-", "").strip()


def reload() -> dict:
    """Re-read settings.json and refresh live knobs. Returns the full settings."""
    s = load_settings()
    try:
        _apply(s)
    except (TypeError, ValueError) as e:
        log.warning("Bad setting value, keeping previous knobs: %s", e)
    return s


# --- Product matching (ported verbatim from the homelab tracker) ----------
def is_valid_product(title: str) -> bool:
    # Single-product legacy mode is unused here; multi-product uses is_valid_for_product.
    return True


def load_products() -> list[dict] | None:
    """Load product definitions from products.json, compiling regex patterns.
    Returns None when the file is absent or empty (nothing to scan)."""
    import os
    if not os.path.isfile(paths.PRODUCTS_FILE):
        return None
    try:
        with open(paths.PRODUCTS_FILE, encoding="utf-8") as f:
            products = json.load(f)
        if not isinstance(products, list) or not products:
            return None
        for p in products:
            raw_valid = p.get("valid_pattern", "")
            p["_valid_re"] = re.compile(raw_valid, re.IGNORECASE) if raw_valid else None
            raw_exclude = p.get("exclude_pattern")
            p["_exclude_re"] = re.compile(raw_exclude, re.IGNORECASE) if raw_exclude else None
        log.info("Loaded %d products from %s", len(products), paths.PRODUCTS_FILE)
        return products
    except Exception as e:
        log.error("Failed to load %s: %s", paths.PRODUCTS_FILE, e)
        return None


def is_valid_for_product(title: str, product: dict) -> bool:
    """Title passes if it matches valid_pattern and not exclude_pattern."""
    exclude_re = product.get("_exclude_re")
    if exclude_re and exclude_re.search(title):
        return False
    valid_re = product.get("_valid_re")
    if valid_re:
        return bool(valid_re.search(title))
    return True


# Apply once at import so constants are sane before the first reload().
_apply(load_settings())
