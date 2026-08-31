"""
Supply Chain Intelligence -- 2026-08-31, Company Network cross-industry
expansion #2 (AJ: "由1開始順住做" -- real estate was #1, this is #2,
search-trends/consumer is #3).

What this is: same shape as services/real_estate_service.py and
services/eia_energy_service.py -- national supply-chain/manufacturing-
throughput indicators paired with the specific tickers they're actually
relevant to (freight/logistics carriers, railroads, transportation
ETFs), never presented as a reading for an unrelated symbol.

Series chosen (all verified live on FRED, U.S. Census Bureau source,
public-domain-citation-requested, no proprietary/subscription data):
- ISRATIO: Total Business Inventories/Sales Ratio -- a rising ratio
  means goods are piling up relative to sales (demand-side slack or
  supply-side overproduction); a falling ratio into multi-year lows can
  signal restocking pressure / tight availability.
- AMTMNO: Manufacturers' New Orders, Total Manufacturing -- forward-
  looking demand signal for the whole production chain.
- DGORDER: Manufacturers' New Orders, Durable Goods -- same signal,
  durable-goods slice (more volatile, more cyclical).
- IPMAN: Industrial Production, Manufacturing (NAICS) -- actual output,
  not just orders.
- MANEMP: All Employees, Manufacturing -- headcount-side capacity signal.

None of these are a literal "supply chain pressure index" (the NY Fed's
GSCPI is published as a standalone spreadsheet, not a FRED series with a
stable API-fetchable series_id, so it's deliberately excluded here --
same "don't fabricate a data path that doesn't reliably exist" standard
applied throughout this codebase) but together they're a real, honestly-
sourced read on manufacturing throughput and inventory tightness, which
is what actually moves freight/logistics-ticker fundamentals.

Zero new API integration, zero new signup: reuses FRED (services/
fred_macro_service.py already established the dormant-until-FRED_API_KEY
convention and the attribution text this module copies verbatim).
Keeps its own independent _fetch_series()/cache/persistence, per this
codebase's per-collector-module-independence convention (see services/
sec_form4_service.py's module docstring for why) -- NOT a shared import
from fred_macro_service.py or real_estate_service.py.

Honesty contract, same as fred_macro_service.py: FRED's "." (missing
observation) is dropped, never coerced to 0 or interpolated. A ticker not
in _TICKER_TO_NAME below gets `None` from get_supply_chain_context_for_
ticker(), not a fabricated "no data" reading dressed up as a real one.
"""
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

FRED_API_KEY_ENV = "FRED_API_KEY"
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
ATTRIBUTION = "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis."

SOURCE_KEY = "supply_chain_fred"
register_source(SOURCE_KEY, "FRED US Manufacturing/Supply Chain", "supply_chain")

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _init_persistence_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS supply_chain_observations (
            series_id TEXT NOT NULL,
            date TEXT NOT NULL,
            value REAL NOT NULL,
            fetched_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (series_id, date)
        )
    """)
    conn.commit()
    conn.close()


_init_persistence_table()


def _persist_observations(series_id: str, observations: list):
    if not observations:
        return
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.executemany(
            """
            INSERT INTO supply_chain_observations (series_id, date, value, fetched_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(series_id, date) DO UPDATE SET value=excluded.value, fetched_at=excluded.fetched_at
            """,
            [(series_id, o["date"], o["value"]) for o in observations],
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("supply_chain_service: failed to persist %s: %s", series_id, e)


def _load_persisted(series_id: str, n_obs: int) -> Optional[list]:
    try:
        conn = sqlite3.connect(_DB_PATH)
        rows = conn.execute(
            "SELECT date, value FROM supply_chain_observations WHERE series_id=? ORDER BY date DESC LIMIT ?",
            (series_id, n_obs),
        ).fetchall()
        conn.close()
        if not rows:
            return None
        return [{"date": d, "value": v} for d, v in reversed(rows)]
    except Exception:
        return None


_SERIES = {
    "inventory_sales_ratio": {"series_id": "ISRATIO", "label": "Total Business Inventories/Sales Ratio", "unit": "ratio"},
    "manufacturing_new_orders_musd": {"series_id": "AMTMNO", "label": "Manufacturers' New Orders: Total Manufacturing", "unit": "$ millions"},
    "durable_goods_orders_musd": {"series_id": "DGORDER", "label": "Manufacturers' New Orders: Durable Goods", "unit": "$ millions"},
    "industrial_production_manufacturing_index": {"series_id": "IPMAN", "label": "Industrial Production: Manufacturing (NAICS)", "unit": "index (2017=100)"},
    "manufacturing_employment_thousands": {"series_id": "MANEMP", "label": "All Employees: Manufacturing", "unit": "thousand persons"},
}

_CACHE_TTL_SECONDS = 6 * 3600
_cache: Dict[str, Dict] = {}


def is_available() -> bool:
    return bool(os.getenv(FRED_API_KEY_ENV))


def _fetch_series(series_id: str, n_obs: int = 1) -> Optional[list]:
    """Returns up to n_obs most recent observations, oldest-first. Same
    in-memory-cache -> persisted-table -> None fallback chain as
    fred_macro_service.py's _fetch_series; kept as an independent copy
    here per this codebase's per-collector-module-independence
    convention."""
    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(series_id)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["observations"]

    if not is_source_enabled(SOURCE_KEY):
        return (cached["observations"] if cached else None) or _load_persisted(series_id, n_obs)

    params = {
        "series_id": series_id,
        "api_key": os.getenv(FRED_API_KEY_ENV),
        "file_type": "json",
        "sort_order": "desc",
        "limit": n_obs,
    }
    record_run_start(SOURCE_KEY)
    try:
        res = get_with_backoff(FRED_BASE_URL, params=params, timeout=10)
        if res.status_code != 200:
            record_run_error(SOURCE_KEY, f"{series_id}: HTTP {res.status_code}")
            return (cached["observations"] if cached else None) or _load_persisted(series_id, n_obs)
        payload = res.json()
    except Exception as e:
        logger.info("supply_chain_service: failed to fetch %s: %s", series_id, e)
        record_run_error(SOURCE_KEY, f"{series_id}: {e}")
        return (cached["observations"] if cached else None) or _load_persisted(series_id, n_obs)

    rows = payload.get("observations") or []
    observations = []
    for row in reversed(rows):
        raw_value = row.get("value")
        if raw_value in (None, ".", ""):
            continue
        try:
            observations.append({"date": row.get("date"), "value": round(float(raw_value), 3)})
        except (TypeError, ValueError):
            continue

    if observations:
        _cache[series_id] = {"fetched_at": now, "observations": observations}
        _persist_observations(series_id, observations)
        record_run_success(SOURCE_KEY)
        return observations
    record_run_error(SOURCE_KEY, f"{series_id}: fetch returned zero usable observations")
    return (cached["observations"] if cached else None) or _load_persisted(series_id, n_obs)


# Freight carriers, railroads, logistics operators, and 2 transportation
# ETFs -- tickers whose fundamentals are directly, mechanically exposed
# to manufacturing throughput and inventory cycles (they physically move
# the goods these indicators measure). Deliberately NOT every ticker
# with "supply chain" in its business description -- same conservative-
# linkage reasoning as eia_energy_service.py's USO/UNG-only scope.
_TICKER_TO_NAME = {
    "FDX": "FedEx", "UPS": "United Parcel Service", "XPO": "XPO Inc",
    "JBHT": "J.B. Hunt Transport Services", "CHRW": "C.H. Robinson Worldwide",
    "ODFL": "Old Dominion Freight Line", "GXO": "GXO Logistics",
    "EXPD": "Expeditors International of Washington",
    "CSX": "CSX Corporation", "UNP": "Union Pacific Corporation", "NSC": "Norfolk Southern Corporation",
    "IYT": "iShares Transportation Average ETF", "XTN": "SPDR S&P Transportation ETF",
}


def get_supply_chain_context_for_ticker(ticker: str) -> Optional[Dict]:
    """Returns {"matched_ticker": "FDX", "matched_name": "FedEx",
    "attribution": "...", "indicators": {series_key: {...} or None}}
    or None if this ticker has no supply-chain/freight linkage at all
    (never a fabricated reading for an unrelated symbol)."""
    ticker = (ticker or "").upper().strip()
    name = _TICKER_TO_NAME.get(ticker)
    if not name:
        return None
    if not is_available():
        return {"matched_ticker": ticker, "matched_name": name, "available": False,
                "message": f"{FRED_API_KEY_ENV} 未設定，供應鏈數據暫時未開放。"}

    indicators: Dict[str, Optional[Dict]] = {}
    for key, meta in _SERIES.items():
        obs = _fetch_series(meta["series_id"], n_obs=1)
        indicators[key] = (
            {"label": meta["label"], "unit": meta["unit"], "date": obs[-1]["date"], "value": obs[-1]["value"]}
            if obs else None
        )

    return {
        "matched_ticker": ticker,
        "matched_name": name,
        "attribution": ATTRIBUTION,
        "indicators": indicators,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_supply_chain_context_for_ticker("FDX"), indent=2, ensure_ascii=False))
