"""End-to-end engine verification (Linux dev). Seeds products.json with two
cuts (patinho + bacalhau), runs a live scan, and prints the resulting R$/kg
rows + notification split. No GUI, no Windows deps."""
import asyncio
import json
import os
import sys

# Make `engine` importable (app/ on path) and force a throwaway data dir.
HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "..", "app")
sys.path.insert(0, APP)

DATA = os.path.join(HERE, "_tmp_data")
os.makedirs(DATA, exist_ok=True)
# Point paths at the temp dir before importing engine.
os.environ["APPDATA"] = DATA
os.environ["XDG_DATA_HOME"] = DATA

# Neutralise the portable ./data detection by making the repo root unwritable
# is overkill; instead monkeypatch paths after import.
import engine.paths as paths  # noqa: E402
paths.DATA_DIR = __import__("pathlib").Path(DATA)
paths.DB_PATH = os.path.join(DATA, "prices.db")
paths.PRODUCTS_FILE = os.path.join(DATA, "products.json")
paths.SETTINGS_FILE = os.path.join(DATA, "settings.json")

from engine import config, products, database  # noqa: E402
from engine.scanner import run_scan  # noqa: E402

# Settings: real Brasília CEP for DF pricing, notifications OFF (dry run).
config.save_settings({
    "brasilia_cep": "71687206",
    "notifications_enabled": False,
    "max_pages": 2,
})

PRODUCTS = [
    {
        "name": "Patinho (peça/bife)",
        "swift_categories": ["bovinos/patinho"],
        "search_samsclub": ["patinho"],
        "search_superadega": ["patinho"],
        "valid_pattern": "patinho",
        "exclude_pattern": "mo[ií]d|strogonoff|empanad|temperad|hamb[uú]rguer|kafta|alm[oô]ndega|rechead|espeto",
        "require_kg": False, "condition": "novo", "notify_new": True,
        "min_price": 0, "max_price": 0,
    },
    {
        "name": "Bacalhau (lombo/posta)",
        "swift_categories": ["pescados/bacalhau"],
        "search_samsclub": ["bacalhau"],
        "search_superadega": ["bacalhau"],
        "valid_pattern": "bacalhau|saithe",
        "exclude_pattern": "desfiad|bolinho|croquete|past[eé]l|risoto|empanad|nugget|petisco",
        "require_kg": True, "condition": "novo", "notify_new": True,
        "min_price": 0, "max_price": 0,
    },
]

with open(paths.PRODUCTS_FILE, "w", encoding="utf-8") as f:
    json.dump(PRODUCTS, f, ensure_ascii=False, indent=2)


async def main():
    result = await run_scan()
    print(f"\n=== ScanResult: {result.total_found} found, {len(result.new)} new, "
          f"{len(result.drops)} drops, {len(result.new_lows)} new-lows, "
          f"{len(result.errors)} errors ===")
    for e in result.errors:
        print("  ERROR:", e)

    db = database.get_db()
    try:
        print("\n--- Item summary (current lowest R$/kg per cut) ---")
        for row in database.get_item_summary(db):
            lo = database.get_lowest_ever_ppk(db, row["model_family"])
            print(f"  {row['model_family']:26} atual {row['current_ppk']!s:>7} R$/kg "
                  f"@ {row['cheapest_site']:10} · {row['n_offers']} ofertas · "
                  f"menor histórico {lo['ppk'] if lo else '-'}")
        print("\n--- Listings (cheapest 12) ---")
        for r in database.get_listings(db, limit=12):
            print(f"  {r['site']:10} {r['price_per_kg']!s:>7} R$/kg  (pac {r['price']})  "
                  f"[{r['model_family']}]  {r['title'][:44]}")
    finally:
        db.close()

    # Assertions
    db = database.get_db()
    n = db.execute("SELECT COUNT(*) c FROM products WHERE price_per_kg IS NOT NULL").fetchone()["c"]
    fams = [r["model_family"] for r in db.execute(
        "SELECT DISTINCT model_family FROM products").fetchall()]
    db.close()
    assert n > 0, "no priced rows landed"
    assert any("Bacalhau" in (f or "") for f in fams), "bacalhau missing"
    assert any("Patinho" in (f or "") for f in fams), "patinho missing"
    print("\n✅ assertions passed:", n, "priced rows across", fams)


if __name__ == "__main__":
    asyncio.run(main())
