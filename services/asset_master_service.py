"""2026-08-26 (AJ's "Data Factory" batch, foundation layer part 2):
entity resolution -- one canonical asset_id per real-world asset, with
aliases mapping every ticker/name variant back to it.

Why this exists: confirmed via audit that nothing in this codebase does
entity resolution today. crypto_service.py, fundamentals_service.py,
smart_beta_service.py, capital_flow_engine.py etc. all key off whatever
ticker string a caller happens to pass in -- "GOOGL"/"GOOG"/"Alphabet"
are three unrelated strings with no shared identity. Every future
collector (SEC EDGAR ownership, CFTC COT, cross-exchange crypto, non-US
tickers) needs a shared join key, or nothing they collect can ever be
combined into one picture of "this asset". This table is that join key.

Kept deliberately minimal for this foundation step: no ownership/control
edges yet (that's Step 5, pending AJ's go-ahead), just asset identity +
alias resolution + a bare entity table for the future ownership graph to
reference. SQLite, same xfinlab.db as everything else -- see
data_source_registry.py's docstring for why this is SQLite and not
Postgres.
"""
import os
import re
import sqlite3
import uuid
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_tables():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS asset_master (
            asset_id TEXT PRIMARY KEY,
            primary_ticker TEXT,
            name TEXT,
            asset_class TEXT,
            exchange TEXT,
            currency TEXT,
            country TEXT,
            sector TEXT,
            isin TEXT,
            figi TEXT,
            cik TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_master (
            entity_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            entity_type TEXT,
            country TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS asset_alias (
            alias TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            alias_type TEXT NOT NULL,
            PRIMARY KEY (alias, alias_type)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_asset_alias_asset_id ON asset_alias(asset_id)")
    conn.commit()
    conn.close()


_init_tables()


def _normalize_alias(alias: str) -> str:
    return re.sub(r"\s+", " ", alias.strip()).upper()


def upsert_asset(
    primary_ticker: str,
    name: str,
    asset_class: str = "equity",
    exchange: Optional[str] = None,
    currency: Optional[str] = None,
    country: Optional[str] = None,
    sector: Optional[str] = None,
    isin: Optional[str] = None,
    figi: Optional[str] = None,
    cik: Optional[str] = None,
    asset_id: Optional[str] = None,
) -> str:
    """Creates a new asset (auto-registering its primary_ticker as a
    'ticker' alias) or updates an existing one if asset_id is given.
    Returns the asset_id either way -- callers that don't already know
    the asset_id should use resolve_asset(primary_ticker) first to avoid
    creating a duplicate row for an asset that already exists."""
    conn = _get_db()
    if asset_id is None:
        existing = conn.execute(
            "SELECT asset_id FROM asset_alias WHERE alias=? AND alias_type='ticker'",
            (_normalize_alias(primary_ticker),),
        ).fetchone()
        asset_id = existing["asset_id"] if existing else f"AST-{uuid.uuid4().hex[:12]}"

    conn.execute(
        """
        INSERT INTO asset_master (asset_id, primary_ticker, name, asset_class, exchange, currency, country, sector, isin, figi, cik)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_id) DO UPDATE SET
            primary_ticker=excluded.primary_ticker,
            name=excluded.name,
            asset_class=excluded.asset_class,
            exchange=COALESCE(excluded.exchange, asset_master.exchange),
            currency=COALESCE(excluded.currency, asset_master.currency),
            country=COALESCE(excluded.country, asset_master.country),
            sector=COALESCE(excluded.sector, asset_master.sector),
            isin=COALESCE(excluded.isin, asset_master.isin),
            figi=COALESCE(excluded.figi, asset_master.figi),
            cik=COALESCE(excluded.cik, asset_master.cik),
            updated_at=datetime('now')
        """,
        (asset_id, primary_ticker, name, asset_class, exchange, currency, country, sector, isin, figi, cik),
    )
    conn.execute(
        "INSERT INTO asset_alias (alias, asset_id, alias_type) VALUES (?, ?, 'ticker') ON CONFLICT(alias, alias_type) DO UPDATE SET asset_id=excluded.asset_id",
        (_normalize_alias(primary_ticker), asset_id),
    )
    conn.commit()
    conn.close()
    return asset_id


def add_alias(alias: str, asset_id: str, alias_type: str = "alt_ticker"):
    """alias_type examples: 'ticker' (primary/other exchange tickers),
    'alt_ticker' (e.g. GOOG vs GOOGL), 'name' (e.g. 'Alphabet', 'Google'),
    'isin', 'cik'. Multiple alias_types can point the same alias string
    at the same asset without conflict since alias_type is part of the
    primary key."""
    conn = _get_db()
    conn.execute(
        "INSERT INTO asset_alias (alias, asset_id, alias_type) VALUES (?, ?, ?) ON CONFLICT(alias, alias_type) DO UPDATE SET asset_id=excluded.asset_id",
        (_normalize_alias(alias), asset_id, alias_type),
    )
    conn.commit()
    conn.close()


def resolve_asset(alias: str) -> Optional[str]:
    """Case/whitespace-insensitive lookup across every alias_type. Returns
    the asset_id, or None if this string has never been seen before."""
    conn = _get_db()
    row = conn.execute(
        "SELECT asset_id FROM asset_alias WHERE alias=? LIMIT 1",
        (_normalize_alias(alias),),
    ).fetchone()
    conn.close()
    return row["asset_id"] if row else None


def get_asset(asset_id: str) -> Optional[dict]:
    conn = _get_db()
    row = conn.execute("SELECT * FROM asset_master WHERE asset_id=?", (asset_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_entity(name: str, entity_type: str = "corporation", country: Optional[str] = None, entity_id: Optional[str] = None) -> str:
    """entity_master is intentionally separate from asset_master: an
    entity (e.g. a fund manager, a holding company) is a legal/economic
    actor, not something that trades on its own -- this is the row the
    future ownership/control graph (Step 5) will point FROM, while
    asset_master rows are what it points TO."""
    conn = _get_db()
    if entity_id is None:
        entity_id = f"ENT-{uuid.uuid4().hex[:12]}"
    conn.execute(
        "INSERT INTO entity_master (entity_id, name, entity_type, country) VALUES (?, ?, ?, ?) ON CONFLICT(entity_id) DO UPDATE SET name=excluded.name, entity_type=excluded.entity_type, country=COALESCE(excluded.country, entity_master.country)",
        (entity_id, name, entity_type, country),
    )
    conn.commit()
    conn.close()
    return entity_id


def list_assets(limit: int = 100) -> list:
    conn = _get_db()
    rows = conn.execute("SELECT * FROM asset_master ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
