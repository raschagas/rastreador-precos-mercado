"""Supermarket scrapers — pure httpx (no browser). Ported from the homelab
tracker's grocery path; the electronics/Playwright scrapers are intentionally
dropped. Three data sources:

- Sam's Club (VTEX): full-text ``?ft=`` search.
- Swift (VTEX): category-path search (its ``?ft=`` returns []).
- Superadega (Instabuy / ibecom backend): search by term, pinned by store id.

Everything is normalised to R$/kg via :func:`engine.pricing.price_per_kg`.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from datetime import datetime, timezone
from urllib.parse import urlencode, quote

import httpx

from . import config
from .config import (
    SAMS_HOST, SWIFT_HOST, VTEX_PAGE_SIZE,
    SUPERADEGA_STORE_ID, IBECOM_SEARCH_URL, SUPERADEGA_SITE_URL,
    is_valid_product,
)
from .database import get_db, upsert_product, log_scan
from .pricing import price_per_kg

log = logging.getLogger(__name__)


def _make_id(site: str, text: str) -> str:
    return hashlib.md5(f"{site}:{text}".encode()).hexdigest()[:16]


async def _delay():
    await asyncio.sleep(random.uniform(config.PAGE_DELAY_MIN, config.PAGE_DELAY_MAX))


# ── VTEX (Sam's Club + Swift) ────────────────────────────────────────────────
_VTEX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

_region_cache: dict[str, str | None] = {}


async def resolve_region(host: str, cep: str) -> str | None:
    """Resolve a VTEX regionId for a CEP so we see DF pricing/availability.

    Without a regionId many items come back Price=0 / IsAvailable=false. Cached
    per (host, cep). Fail-safe: returns None on any error (site default region)."""
    if not cep:
        return None
    key = f"{host}:{cep}"
    if key in _region_cache:
        return _region_cache[key]
    region_id = None
    try:
        async with httpx.AsyncClient(timeout=20, headers=_VTEX_HEADERS) as client:
            resp = await client.get(
                f"https://{host}/api/checkout/pub/regions",
                params={"country": "BRA", "postalCode": cep},
            )
            if resp.status_code in (200, 206):
                data = resp.json()
                if isinstance(data, list) and data:
                    region_id = data[0].get("id")
    except Exception as e:
        log.warning("VTEX region resolve failed for %s (cep=%s): %s", host, cep, e)
    _region_cache[key] = region_id
    log.info("VTEX region for %s (cep=%s) -> %s", host, cep, region_id)
    return region_id


async def _vtex_fetch(host: str, *, ft: str | None = None, category: str | None = None,
                      region_id: str | None = None,
                      client: httpx.AsyncClient | None = None) -> list[dict]:
    """Fetch raw VTEX catalog products (paginated) via ft or category path."""
    if category:
        base = f"https://{host}/api/catalog_system/pub/products/search/{category}"
    else:
        base = f"https://{host}/api/catalog_system/pub/products/search"

    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=30, headers=_VTEX_HEADERS)

    products: list[dict] = []
    try:
        for page_num in range(config.MAX_PAGES):
            _from = page_num * VTEX_PAGE_SIZE
            _to = _from + VTEX_PAGE_SIZE - 1
            params = {"_from": _from, "_to": _to}
            if ft:
                params["ft"] = ft
            if region_id:
                params["regionId"] = region_id
            # Encode spaces as %20 (quote), NOT '+' — VTEX 400s on '+' in ?ft=.
            url = f"{base}?{urlencode(params, quote_via=quote)}"
            try:
                resp = await client.get(url)
            except Exception as e:
                log.warning("VTEX fetch error %s (%s): %s", host, category or ft, e)
                break
            if resp.status_code not in (200, 206):
                log.warning("VTEX %s status %d for %s", host, resp.status_code, category or ft)
                break
            try:
                batch = resp.json()
            except Exception as e:
                log.warning("VTEX %s bad JSON for %s: %s", host, category or ft, e)
                break
            if not isinstance(batch, list) or not batch:
                break
            products.extend(batch)
            if len(batch) < VTEX_PAGE_SIZE:
                break
            await _delay()
    finally:
        if own:
            await client.aclose()
    return products


def _vtex_extract(raw: dict, site: str, host: str, model_family, project, condition) -> dict | None:
    """Cheapest available SKU/seller offer -> listing dict with R$/kg."""
    name = (raw.get("productName") or "").strip()
    if not name:
        return None
    best = None  # (price, measurement_unit, unit_multiplier)
    for item in raw.get("items") or []:
        unit = item.get("measurementUnit")
        mult = item.get("unitMultiplier")
        for seller in item.get("sellers") or []:
            offer = seller.get("commertialOffer") or {}
            price = offer.get("Price") or 0
            if offer.get("IsAvailable") and price and price > 0:
                if best is None or price < best[0]:
                    best = (float(price), unit, mult)
    if best is None:
        return None
    price, unit, mult = best
    link = raw.get("link") or ""
    if not link:
        slug = raw.get("linkText")
        link = f"https://{host}/{slug}/p" if slug else ""
    ext_id = str(raw.get("productId") or "").strip() or _make_id(site, name)
    return {
        "site": site,
        "external_id": ext_id,
        "title": name,
        "price": round(price, 2),
        "condition": condition,
        "seller": None,
        "url": link,
        "model_family": model_family,
        "price_per_kg": price_per_kg(price, unit in ("kg", "g"), name),
        "project": project,
    }


def _vtex_range_ok(price: float, min_p: float, max_p: float) -> bool:
    if min_p and price < min_p:
        return False
    if max_p and price > max_p:
        return False
    return price > 0


def _keep_listing(item, valid_fn, min_price, max_price, require_kg) -> bool:
    """Shared filter for grocery listings (VTEX + Superadega)."""
    if item is None:
        return False
    title = item["title"]
    if valid_fn:
        if not valid_fn(title):
            return False
    elif not is_valid_product(title):
        return False
    if require_kg and item.get("price_per_kg") is None:
        return False
    return _vtex_range_ok(item["price"], min_price, max_price)


def _persist_listings(site, items, model_family, started) -> list[dict]:
    """Upsert extracted+validated listings; return new + price-drop results."""
    log.info("%s: %d products (model=%s)", site, len(items), model_family)
    db = get_db()
    results = []
    try:
        for p in items:
            pid, is_new, old_price = upsert_product(db, **p)
            enriched = {**p, "id": pid}
            if is_new:
                results.append({**enriched, "is_new": True})
            elif old_price and old_price > p["price"]:
                results.append({**enriched, "is_new": False, "old_price": old_price})
        log_scan(db, site, 1, len(items), started, model_family=model_family)
        db.commit()
    finally:
        db.close()
    return results


def _vtex_persist(site, raw_products, model_family, project, condition, host,
                  valid_fn, min_price, max_price, started, require_kg=False) -> list[dict]:
    listings: dict[str, dict] = {}
    for raw in raw_products:
        item = _vtex_extract(raw, site, host, model_family, project, condition)
        if _keep_listing(item, valid_fn, min_price, max_price, require_kg):
            listings[item["external_id"]] = item  # dedup by product id
    return _persist_listings(site, list(listings.values()), model_family, started)


async def scrape_samsclub(tokens, *, model_family=None, min_price=0, max_price=0,
                          valid_fn=None, project=None, condition="novo",
                          require_kg=False) -> list[dict]:
    """Sam's Club (VTEX) — full-text search, one request set per token."""
    site = "samsclub"
    started = datetime.now(timezone.utc).isoformat()
    if isinstance(tokens, str):
        tokens = [tokens]
    region_id = await resolve_region(SAMS_HOST, config.BRASILIA_CEP)
    raw: list[dict] = []
    async with httpx.AsyncClient(timeout=30, headers=_VTEX_HEADERS) as client:
        for token in tokens:
            if not token:
                continue
            raw.extend(await _vtex_fetch(SAMS_HOST, ft=token, region_id=region_id, client=client))
    return _vtex_persist(site, raw, model_family, project, condition, SAMS_HOST,
                         valid_fn, min_price, max_price, started, require_kg)


async def scrape_swift(categories, *, model_family=None, min_price=0, max_price=0,
                       valid_fn=None, project=None, condition="novo",
                       require_kg=False) -> list[dict]:
    """Swift (VTEX) — category-path search (its ?ft= endpoint returns [])."""
    site = "swift"
    started = datetime.now(timezone.utc).isoformat()
    if isinstance(categories, str):
        categories = [categories]
    region_id = await resolve_region(SWIFT_HOST, config.BRASILIA_CEP)
    raw: list[dict] = []
    async with httpx.AsyncClient(timeout=30, headers=_VTEX_HEADERS) as client:
        for cat in categories:
            if not cat:
                continue
            raw.extend(await _vtex_fetch(SWIFT_HOST, category=cat.strip("/"),
                                         region_id=region_id, client=client))
    return _vtex_persist(site, raw, model_family, project, condition, SWIFT_HOST,
                         valid_fn, min_price, max_price, started, require_kg)


# ── Superadega (Instabuy / ibecom backend) ───────────────────────────────────
_IBECOM_PAGE_SIZE = 50


async def _ibecom_fetch(term: str, *, client: httpx.AsyncClient) -> list[dict]:
    """Fetch raw ibecom product rows for a search term (paginated)."""
    headers = {"x-store-id": SUPERADEGA_STORE_ID, "Content-Type": "application/json"}
    products: list[dict] = []
    for page in range(1, config.MAX_PAGES + 1):
        params = {"search": term, "page": page, "N": _IBECOM_PAGE_SIZE}
        url = f"{IBECOM_SEARCH_URL}?{urlencode(params, quote_via=quote)}"
        try:
            resp = await client.get(url, headers=headers)
        except Exception as e:
            log.warning("ibecom fetch error (%s): %s", term, e)
            break
        if resp.status_code not in (200, 206):
            log.warning("ibecom status %d for %s", resp.status_code, term)
            break
        try:
            data = resp.json()
        except Exception as e:
            log.warning("ibecom bad JSON for %s: %s", term, e)
            break
        rows = data.get("data") or [] if isinstance(data, dict) else []
        products.extend(x for x in rows if x.get("item_type") == "product")
        if len(rows) < _IBECOM_PAGE_SIZE:
            break
        await _delay()
    return products


def _ibecom_extract(raw: dict, model_family, project, condition) -> dict | None:
    """Turn a raw ibecom product into a listing dict (R$/kg via unit_type)."""
    name = (raw.get("name") or "").strip()
    if not name:
        return None
    if not (raw.get("stock") or {}).get("has_available_stock", True):
        return None
    pc = raw.get("price_config") or {}
    price = raw.get("min_price_valid") or pc.get("price")
    if not price or price <= 0:
        return None
    price = float(price)
    ppk = price_per_kg(price, (raw.get("unit_type") or "").upper() == "KG", name)
    slug = raw.get("slug") or ""
    url = f"{SUPERADEGA_SITE_URL}/p/{slug}" if slug else SUPERADEGA_SITE_URL
    ext_id = str(raw.get("id") or "").strip() or _make_id("superadega", name)
    return {
        "site": "superadega",
        "external_id": ext_id,
        "title": name,
        "price": round(price, 2),
        "condition": condition,
        "seller": None,
        "url": url,
        "model_family": model_family,
        "price_per_kg": ppk,
        "project": project,
    }


async def scrape_superadega(tokens, *, model_family=None, min_price=0, max_price=0,
                            valid_fn=None, project=None, condition="novo",
                            require_kg=False) -> list[dict]:
    """Superadega (Instabuy/ibecom) — search by term, one request set per token."""
    site = "superadega"
    started = datetime.now(timezone.utc).isoformat()
    if isinstance(tokens, str):
        tokens = [tokens]
    listings: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=30, headers=_VTEX_HEADERS) as client:
        for term in tokens:
            if not term:
                continue
            for raw in await _ibecom_fetch(term, client=client):
                item = _ibecom_extract(raw, model_family, project, condition)
                if _keep_listing(item, valid_fn, min_price, max_price, require_kg):
                    listings[item["external_id"]] = item
    return _persist_listings(site, list(listings.values()), model_family, started)
