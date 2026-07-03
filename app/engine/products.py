"""products.json CRUD + validation. Ported from the tracker-dashboard adapter,
pydantic dropped for a dependency-light plain-dict validator. The whole file is
kept daemon-loadable: unique non-empty names + both regexes compile (exactly
what :func:`engine.config.load_products` needs)."""
from __future__ import annotations

import json
import logging
import os
import re

from . import paths

log = logging.getLogger(__name__)

# Fields persisted per item (regex-compiled ``_valid_re``/``_exclude_re`` and
# any other private keys are stripped before writing).
FIELDS = ("name", "search_samsclub", "swift_categories", "search_superadega",
          "valid_pattern", "exclude_pattern", "require_kg", "condition",
          "notify_new", "min_price", "max_price")

LIST_FIELDS = ("search_samsclub", "swift_categories", "search_superadega")


def _clean(item: dict) -> dict:
    """Keep only public fields, normalise list/number/bool types."""
    out = {}
    for k in FIELDS:
        if k not in item:
            continue
        v = item[k]
        if k in LIST_FIELDS:
            out[k] = _as_list(v)
        elif k in ("min_price", "max_price"):
            try:
                out[k] = float(v or 0)
            except (TypeError, ValueError):
                out[k] = 0.0
        elif k in ("require_kg", "notify_new"):
            out[k] = bool(v)
        else:
            out[k] = v
    out.setdefault("condition", "novo")
    out.setdefault("notify_new", True)
    out.setdefault("require_kg", False)
    out.setdefault("min_price", 0.0)
    out.setdefault("max_price", 0.0)
    return out


def _as_list(v) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [s.strip() for s in v.split(",") if s.strip()]
    return []


def list_items() -> list[dict]:
    if not os.path.isfile(paths.PRODUCTS_FILE):
        return []
    try:
        with open(paths.PRODUCTS_FILE, encoding="utf-8") as f:
            items = json.load(f)
        return items if isinstance(items, list) else []
    except Exception as e:
        log.error("Failed to read %s: %s", paths.PRODUCTS_FILE, e)
        return []


def get_item(name: str) -> dict | None:
    return next((it for it in list_items() if it.get("name") == name), None)


def _validate_all(items: list) -> None:
    seen = set()
    for it in items:
        nm = (it.get("name") or "").strip()
        if not nm:
            raise ValueError("todo item precisa de um nome não-vazio")
        if nm in seen:
            raise ValueError(f"nome de item duplicado: {nm!r}")
        seen.add(nm)
        for key in ("valid_pattern", "exclude_pattern"):
            pat = it.get(key) or ""
            if pat:
                try:
                    re.compile(pat, re.IGNORECASE)
                except re.error as e:
                    raise ValueError(f"{nm}: {key} inválido: {e}")
        if not (_as_list(it.get("search_samsclub")) or _as_list(it.get("swift_categories"))
                or _as_list(it.get("search_superadega"))):
            raise ValueError(f"{nm}: informe ao menos uma busca de loja "
                             "(Sam's, Swift ou Superadega)")


def _write(items: list) -> None:
    tmp = paths.PRODUCTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, paths.PRODUCTS_FILE)


def add_item(data: dict) -> dict:
    items = list_items()
    validated = _clean(data or {})
    if not (validated.get("name") or "").strip():
        raise ValueError("informe um nome")
    if any(it.get("name") == validated["name"] for it in items):
        raise ValueError(f"já existe um item chamado {validated['name']!r}")
    items.append(validated)
    _validate_all(items)
    _write(items)
    log.info("added item %r", validated["name"])
    return validated


def edit_item(name: str, data: dict) -> dict:
    items = list_items()
    idx = next((i for i, it in enumerate(items) if it.get("name") == name), None)
    if idx is None:
        raise KeyError(name)
    merged = dict(items[idx])
    merged.update(data or {})
    validated = _clean(merged)
    new_name = validated["name"]
    if new_name != name and any(it.get("name") == new_name for it in items):
        raise ValueError(f"já existe um item chamado {new_name!r}")
    items[idx] = validated
    _validate_all(items)
    _write(items)
    log.info("edited item %r", name)
    return validated


def remove_item(name: str) -> None:
    items = list_items()
    kept = [it for it in items if it.get("name") != name]
    if len(kept) == len(items):
        raise KeyError(name)
    _write(kept)
    log.info("removed item %r", name)
