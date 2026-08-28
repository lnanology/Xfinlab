"""
CBOE VIX Term Structure Service -- 2026-08-28 (AJ: "咁你一次過起").

Why this fills a real gap: nothing in the Data Factory so far measures
the OPTIONS market's own view of future volatility. CFTC COT shows fund
POSITIONING and EIA/Treasury/USDA show physical/fiscal FUNDAMENTALS, but
none of them touch implied volatility -- the VIX term structure (9-day,
30-day "the VIX", 3-month, 6-month) is the market's own forward-looking
fear gauge, and its SHAPE (contango vs backwardation) is a well-known
regime signal: normal markets see VIX9D < VIX < VIX3M < VIX6M (contango,
calm/complacent); a spike inverting that curve (backwardation) means the
market is pricing near-term panic higher than medium-term, historically
coinciding with market stress (2020 COVID crash, 2008 GFC, etc.).

Source: CBOE's own public historical-data CSVs (cdn.cboe.com), free, no
key, no registration -- these are the same daily-updated CSV files CBOE
publishes for its own website's historical charts. Confirmed reachable
during this build (VIX_History.csv). Four index codes:
  - VIX9D  -- 9-day expected volatility
  - VIX    -- the classic 30-day VIX
  - VIX3M  -- 3-month expected volatility
  - VIX6M  -- 6-month expected volatility

Honesty note on CSV column names: CBOE's historical CSVs are not
perfectly uniform across index files (older exports used slightly
different header casing/spacing across index products). This module
parses defensively -- it looks for a column containing "CLOSE"
case-insensitively rather than assuming an exact header string, and a
file that doesn't parse at all is recorded as a live run error (via
record_run_error) rather than silently fabricated, same as every other
collector here.
"""
import csv
import io
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional

from services.outbound_http import get_with_backoff
from services.data_source_registry import (
    register_source, is_source_enabled, record_run_start,
    record_run_success, record_run_error,
)

logger = logging.getLogger(__name__)

ATTRIBUTION = "Data sourced from Cboe Global Markets historical index data (cdn.cboe.com). Not endorsed or certified by Cboe. For research reference only, not investment advice."

SOURCE_KEY = "cboe_vix_term_structure"
register_source(SOURCE_KEY, "CBOE VIX Term Structure", "volatility")

_INDEX_URLS = {
    "vix9d": ("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX9D_History.csv", "VIX9D (9-Day Volatility)"),
    "vix": ("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv", "VIX (30-Day Volatility)"),
    "vix3m": ("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv", "VIX3M (3-Month Volatility)"),
    "vix6m": ("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX6M_History.csv", "VIX6M (6-Month Volatility)"),
}

_CACHE_TTL_SECONDS = 6 * 3600  # daily series -- refresh a few times a day at most
_cache: Dict[str, Dict] = {}  # index_key -> {"fetched_at": epoch, "date": "...", "close": ...}

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _init_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cboe_vix_observations (
            index_key TEXT NOT NULL,
            date TEXT NOT NULL,
            close REAL,
            fetched_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (index_key, date)
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def is_available() -> bool:
    return True  # no API key required


def _persist(index_key: str, date_str: str, close: float):
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            """
            INSERT INTO cboe_vix_observations (index_key, date, close, fetched_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(index_key, date) DO UPDATE SET close=excluded.close, fetched_at=excluded.fetched_at
            """,
            (index_key, date_str, close),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("cboe_vix_service: failed to persist %s: %s", index_key, e)


def _load_persisted(index_key: str) -> Optional[dict]:
    try:
        conn = sqlite3.connect(_DB_PATH)
        row = conn.execute(
            "SELECT date, close FROM cboe_vix_observations WHERE index_key=? ORDER BY date DESC LIMIT 1",
            (index_key,),
        ).fetchone()
        conn.close()
        return {"date": row[0], "close": row[1]} if row else None
    except Exception:
        return None


def _parse_latest_close(csv_text: str) -> Optional[dict]:
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    if len(rows) < 2:
        return None
    header = [h.strip() for h in rows[0]]
    close_idx = next((i for i, h in enumerate(header) if "close" in h.lower()), None)
    date_idx = next((i for i, h in enumerate(header) if "date" in h.lower()), 0)
    if close_idx is None:
        return None
    last_row = rows[-1]
    try:
        close = float(last_row[close_idx])
        date_str = last_row[date_idx].strip()
    except (ValueError, IndexError):
        return None
    return {"date": date_str, "close": close}


def _fetch_index(index_key: str) -> Optional[dict]:
    """Returns {"date": ..., "close": ...} for the most recent trading
    day, or None if live, cache, AND persisted DB all have nothing."""
    url, _ = _INDEX_URLS[index_key]
    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(index_key)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return {"date": cached["date"], "close": cached["close"]}

    if not is_source_enabled(SOURCE_KEY):
        return {"date": cached["date"], "close": cached["close"]} if cached else _load_persisted(index_key)

    record_run_start(SOURCE_KEY)
    try:
        res = get_with_backoff(url, timeout=15)
        if res.status_code != 200:
            logger.info("cboe_vix_service: %s returned HTTP %s", index_key, res.status_code)
            record_run_error(SOURCE_KEY, f"{index_key}: HTTP {res.status_code}")
            return {"date": cached["date"], "close": cached["close"]} if cached else _load_persisted(index_key)
        parsed = _parse_latest_close(res.text)
    except Exception as e:
        logger.info("cboe_vix_service: failed to fetch %s: %s", index_key, e)
        record_run_error(SOURCE_KEY, f"{index_key}: {e}")
        return {"date": cached["date"], "close": cached["close"]} if cached else _load_persisted(index_key)

    if not parsed:
        record_run_error(SOURCE_KEY, f"{index_key}: CSV parsed but no usable CLOSE column/row found")
        return {"date": cached["date"], "close": cached["close"]} if cached else _load_persisted(index_key)

    _cache[index_key] = {"fetched_at": now, "date": parsed["date"], "close": parsed["close"]}
    _persist(index_key, parsed["date"], parsed["close"])
    record_run_success(SOURCE_KEY)
    return parsed


def get_snapshot() -> Dict:
    """
    Returns:
        {"available": True, "as_of": "...", "attribution": "...",
         "term_structure": {"vix9d": {"label": ..., "date": ..., "close": ...}, ...},
         "structure": "contango" | "backwardation" | None,
         "vix3m_minus_vix": float or None}
        {"available": False, "message": "..."} -- every index failed
        (live, cache, AND persisted DB all empty).
    """
    term_structure: Dict[str, Optional[dict]] = {}
    for key, (_, label) in _INDEX_URLS.items():
        obs = _fetch_index(key)
        term_structure[key] = {"label": label, "date": obs["date"], "close": obs["close"]} if obs else None

    if all(v is None for v in term_structure.values()):
        return {"available": False, "message": "CBOE VIX term structure暫時未能提供任何數據（可能係首次運行或短暫故障）。"}

    vix = term_structure.get("vix")
    vix3m = term_structure.get("vix3m")
    structure = None
    spread = None
    if vix and vix3m:
        spread = round(vix3m["close"] - vix["close"], 2)
        structure = "contango" if spread > 0 else ("backwardation" if spread < 0 else "flat")

    return {
        "available": True,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "attribution": ATTRIBUTION,
        "term_structure": term_structure,
        "structure": structure,
        "vix3m_minus_vix": spread,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_snapshot(), indent=2, ensure_ascii=False))
