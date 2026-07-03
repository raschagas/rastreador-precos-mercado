"""Small formatting helpers shared by the GUI tabs."""
from __future__ import annotations

from datetime import datetime

SITE_NAMES = {"samsclub": "Sam's Club", "swift": "Swift", "superadega": "Superadega"}


def brl_kg(value) -> str:
    if value in (None, ""):
        return "—"
    return f"R$ {float(value):,.2f}/kg".replace(",", "X").replace(".", ",").replace("X", ".")


def brl(value) -> str:
    if value in (None, ""):
        return "—"
    return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def short_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(iso)[:16]


def site_name(site: str) -> str:
    return SITE_NAMES.get(site, site)
