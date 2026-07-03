"""Scan orchestrator — runs the three grocery scrapers for every tracked
product, concurrently (semaphore + batch delay), and derives the notification
sets. Ported from the homelab tracker's ``_scan_multi`` + ``scheduled_scan``
grocery paths, with the electronics/LLM branches removed."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from . import config
from .config import is_valid_for_product, load_products
from .database import get_db, get_min_price_per_kg, init_db
from .scrapers import scrape_samsclub, scrape_superadega, scrape_swift

log = logging.getLogger(__name__)


@dataclass
class ScanResult:
    total_found: int = 0
    new: list = field(default_factory=list)       # brand-new listings
    drops: list = field(default_factory=list)     # price drops on existing listings
    new_lows: list = field(default_factory=list)  # cheapest new R$/kg per (cut, store)
    errors: list = field(default_factory=list)


def _as_list(v) -> list:
    if isinstance(v, str):
        return [v] if v else []
    return v or []


async def run_scan() -> ScanResult:
    """Run a full scan across all tracked products. Reloads settings first so
    GUI edits (CEP, interval, knobs) take effect immediately."""
    config.reload()
    init_db()

    products = load_products()
    if not products:
        log.info("No products to scan")
        return ScanResult()

    sem = asyncio.Semaphore(config.MAX_CONCURRENT_SCRAPERS)

    async def _run(label, coro_factory, notify_new):
        async with sem:
            try:
                log.info("Starting scrape: %s", label)
                results = await coro_factory()
                if not notify_new:
                    results = [r for r in results if not r.get("is_new")]
                return results
            except Exception as e:
                log.error("Scraper %s failed: %s", label, e)
                return [{"__error__": f"{label}: {e}"}]

    # Build tasks grouped by product (for batched execution).
    product_tasks: list[list] = []
    for i, prod in enumerate(products):
        name = prod.get("name", f"Produto {i+1}")
        p_min = prod.get("min_price", config.MIN_PRICE)
        p_max = prod.get("max_price", config.MAX_PRICE)
        notify_new = prod.get("notify_new", True)
        require_kg = bool(prod.get("require_kg", False))
        cond = prod.get("condition", "novo")
        cond = cond if cond in ("novo", "usado") else "novo"

        def valid_fn(title, _p=prod):
            return is_valid_for_product(title, _p)

        tasks = []
        sams = _as_list(prod.get("search_samsclub"))
        if sams:
            tasks.append(_run(
                f"Sam's Club [{name}]",
                lambda t=sams, n=name, mn=p_min, mx=p_max, vf=valid_fn, c=cond, rk=require_kg:
                    scrape_samsclub(t, model_family=n, min_price=mn, max_price=mx,
                                    valid_fn=vf, condition=c, require_kg=rk),
                notify_new))
        swift = _as_list(prod.get("swift_categories"))
        if swift:
            tasks.append(_run(
                f"Swift [{name}]",
                lambda t=swift, n=name, mn=p_min, mx=p_max, vf=valid_fn, c=cond, rk=require_kg:
                    scrape_swift(t, model_family=n, min_price=mn, max_price=mx,
                                 valid_fn=vf, condition=c, require_kg=rk),
                notify_new))
        sadega = _as_list(prod.get("search_superadega"))
        if sadega:
            tasks.append(_run(
                f"Superadega [{name}]",
                lambda t=sadega, n=name, mn=p_min, mx=p_max, vf=valid_fn, c=cond, rk=require_kg:
                    scrape_superadega(t, model_family=n, min_price=mn, max_price=mx,
                                      valid_fn=vf, condition=c, require_kg=rk),
                notify_new))
        if tasks:
            product_tasks.append(tasks)

    # Run in batches of MAX_CONCURRENT_SCRAPERS products, delaying between batches.
    all_results = []
    step = max(1, config.MAX_CONCURRENT_SCRAPERS)
    for batch_idx, start in enumerate(range(0, len(product_tasks), step)):
        batch = product_tasks[start:start + step]
        items = [t for group in batch for t in group]
        if not items:
            continue
        if batch_idx > 0 and config.PRODUCT_BATCH_DELAY > 0:
            await asyncio.sleep(config.PRODUCT_BATCH_DELAY)
        results_lists = await asyncio.gather(*items)
        for sublist in results_lists:
            all_results.extend(sublist)

    # Split results.
    result = ScanResult()
    result.errors = [r["__error__"] for r in all_results if r.get("__error__")]
    clean = [r for r in all_results if not r.get("__error__")]
    result.total_found = len(clean)
    result.new = [r for r in clean if r.get("is_new")]
    result.drops = [r for r in clean if not r.get("is_new") and "old_price" in r]

    # Nova mínima: cheapest NEW R$/kg per (cut, store) that ties the current floor.
    grocery_new = [r for r in result.new
                   if r.get("price_per_kg") and r.get("site") in ("samsclub", "swift", "superadega")]
    if grocery_new:
        db = get_db()
        try:
            seen = set()
            for r in sorted(grocery_new, key=lambda x: x["price_per_kg"]):
                key = (r.get("model_family"), r["site"])
                if key in seen:
                    continue
                floor = get_min_price_per_kg(db, r.get("model_family"), r["site"])
                if floor is not None and r["price_per_kg"] <= floor + 1e-6:
                    result.new_lows.append(r)
                    seen.add(key)
        finally:
            db.close()

    log.info("Scan complete — %d found, %d new, %d drops, %d new-lows, %d errors",
             result.total_found, len(result.new), len(result.drops),
             len(result.new_lows), len(result.errors))
    return result
