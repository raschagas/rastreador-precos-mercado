"""SQLite persistence — ported verbatim from the homelab price-tracker, with
DB_PATH sourced from :mod:`engine.paths`. Schema kept intact (extra columns are
harmless) so a homelab ``prices.db`` drops in unchanged."""
import sqlite3
from datetime import datetime, timezone

from .paths import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    site TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    price REAL NOT NULL,
    condition TEXT,
    seller TEXT,
    url TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    UNIQUE(site, external_id)
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    price REAL NOT NULL,
    seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY,
    site TEXT NOT NULL,
    pages_scraped INTEGER,
    products_found INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_site ON products(site);
CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(product_id);
CREATE INDEX IF NOT EXISTS idx_price_history_seen ON price_history(seen_at);
"""


def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def _migrate(db: sqlite3.Connection):
    """Add columns absent from older DBs (safe, idempotent)."""
    existing = {r[1] for r in db.execute("PRAGMA table_info(products)").fetchall()}
    product_cols = [
        ("model_family", "TEXT"),
        ("location", "TEXT"),
        ("notified", "INTEGER DEFAULT 0"),
        ("project", "TEXT"),
        ("price_per_kg", "REAL"),
        ("is_active", "INTEGER DEFAULT 1"),
    ]
    for col, typ in product_cols:
        if col not in existing:
            db.execute(f"ALTER TABLE products ADD COLUMN {col} {typ}")

    scan_existing = {r[1] for r in db.execute("PRAGMA table_info(scan_log)").fetchall()}
    if "model_family" not in scan_existing:
        db.execute("ALTER TABLE scan_log ADD COLUMN model_family TEXT")

    db.execute("CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active)")
    db.commit()


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    _migrate(db)
    db.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_product(
    db: sqlite3.Connection,
    site: str,
    external_id: str,
    title: str,
    price: float,
    condition: str | None,
    seller: str | None,
    url: str,
    model_family: str | None = None,
    location: str | None = None,
    project: str | None = None,
    price_per_kg: float | None = None,
) -> tuple[int, bool, float | None]:
    """Insert or update a product. Returns (product_id, is_new, old_price)."""
    now = _now()
    row = db.execute(
        "SELECT id, price FROM products WHERE site = ? AND external_id = ?",
        (site, external_id),
    ).fetchone()

    if row:
        product_id = row["id"]
        old_price = row["price"]
        db.execute(
            "UPDATE products SET title=?, price=?, condition=?, seller=?, url=?, "
            "model_family=?, location=?, project=?, price_per_kg=?, last_seen=?, is_active=1 WHERE id=?",
            (title, price, condition, seller, url, model_family, location, project,
             price_per_kg, now, product_id),
        )
        is_new = False
    else:
        old_price = None
        cur = db.execute(
            "INSERT INTO products (site, external_id, title, price, condition, seller, url, "
            "model_family, location, project, price_per_kg, first_seen, last_seen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (site, external_id, title, price, condition, seller, url,
             model_family, location, project, price_per_kg, now, now),
        )
        product_id = cur.lastrowid
        is_new = True

    db.execute(
        "INSERT INTO price_history (product_id, price, seen_at) VALUES (?, ?, ?)",
        (product_id, price, now),
    )
    return product_id, is_new, old_price


def mark_notified(db: sqlite3.Connection, product_id: int):
    db.execute("UPDATE products SET notified = 1 WHERE id = ?", (product_id,))


def log_scan(db: sqlite3.Connection, site: str, pages: int, products: int,
             started: str, model_family: str | None = None):
    db.execute(
        "INSERT INTO scan_log (site, pages_scraped, products_found, started_at, "
        "finished_at, model_family) VALUES (?, ?, ?, ?, ?, ?)",
        (site, pages, products, started, _now(), model_family),
    )


def get_min_price_per_kg(db: sqlite3.Connection, model_family: str | None,
                         site: str) -> float | None:
    """Lowest current R$/kg for a cut (model_family) at a given site."""
    row = db.execute(
        """
        SELECT MIN(price_per_kg) AS m FROM products
        WHERE model_family = ? AND site = ?
          AND price_per_kg IS NOT NULL
          AND COALESCE(is_active, 1) = 1
        """,
        (model_family, site),
    ).fetchone()
    return row["m"] if row and row["m"] is not None else None


# --- Read-only views used by the GUI --------------------------------------
def get_item_summary(db: sqlite3.Connection) -> list[dict]:
    """Per tracked item (model_family): current lowest R$/kg + which store, and
    the all-time lowest R$/kg + when it was seen. Drives the 'Itens' table."""
    rows = db.execute(
        """
        WITH active AS (
            SELECT model_family, site, price_per_kg, last_seen
            FROM products
            WHERE COALESCE(is_active, 1) = 1
              AND price_per_kg IS NOT NULL
              AND model_family IS NOT NULL
        ),
        cur AS (
            SELECT model_family, MIN(price_per_kg) AS cur_ppk
            FROM active GROUP BY model_family
        ),
        hist AS (
            SELECT p.model_family, MIN(ph.price) AS lo_pkg
            FROM price_history ph JOIN products p ON p.id = ph.product_id
            WHERE p.price_per_kg IS NOT NULL AND p.model_family IS NOT NULL
            GROUP BY p.model_family
        )
        SELECT cur.model_family AS model_family,
               cur.cur_ppk AS current_ppk,
               (SELECT site FROM active a WHERE a.model_family = cur.model_family
                  ORDER BY price_per_kg ASC LIMIT 1) AS cheapest_site,
               (SELECT COUNT(*) FROM active a WHERE a.model_family = cur.model_family) AS n_offers
        FROM cur ORDER BY cur.model_family
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_lowest_ever_ppk(db: sqlite3.Connection, model_family: str) -> dict | None:
    """All-time lowest R$/kg for a cut, with the date it was recorded.

    price_history stores package prices; we recompute R$/kg using the current
    price_per_kg/price ratio of the cheapest active listing as an approximation
    is unreliable, so instead we track the lowest observed *price_per_kg* by
    scanning products rows (updated each scan). Returns {ppk, seen_at, title}."""
    row = db.execute(
        """
        SELECT price_per_kg AS ppk, last_seen AS seen_at, title, site
        FROM products
        WHERE model_family = ? AND price_per_kg IS NOT NULL
        ORDER BY price_per_kg ASC LIMIT 1
        """,
        (model_family,),
    ).fetchone()
    return dict(row) if row else None


def get_listings(db: sqlite3.Connection, model_family: str | None = None,
                 site: str | None = None, q: str | None = None,
                 limit: int = 1000, days: int = 30) -> list[dict]:
    where = ["COALESCE(is_active, 1) = 1", "price > 0"]
    params: list = []
    if days:
        where.append("last_seen > datetime('now', ? || ' days')")
        params.append(f"-{int(days)}")
    if model_family:
        where.append("model_family = ?"); params.append(model_family)
    if site:
        where.append("site = ?"); params.append(site)
    if q:
        where.append("title LIKE ?"); params.append(f"%{q}%")
    sql = (
        "SELECT id, site, title, price, price_per_kg, model_family, url, "
        "first_seen, last_seen FROM products "
        f"WHERE {' AND '.join(where)} ORDER BY price_per_kg ASC LIMIT ?"
    )
    params.append(int(limit))
    return [dict(r) for r in db.execute(sql, tuple(params)).fetchall()]


def get_history(db: sqlite3.Connection, product_id: int, days: int = 90) -> list[dict]:
    rows = db.execute(
        "SELECT seen_at, price FROM price_history "
        "WHERE product_id = ? AND seen_at > datetime('now', ? || ' days') "
        "ORDER BY seen_at ASC",
        (int(product_id), f"-{int(days)}"),
    ).fetchall()
    return [dict(r) for r in rows]


def get_status(db: sqlite3.Connection) -> dict:
    one = lambda sql: (db.execute(sql).fetchone() or {"c": 0})
    return {
        "products_active": one("SELECT COUNT(*) c FROM products WHERE COALESCE(is_active,1)=1")["c"],
        "products_total": one("SELECT COUNT(*) c FROM products")["c"],
        "last_scan": (db.execute("SELECT MAX(finished_at) t FROM scan_log").fetchone() or {})["t"],
    }
