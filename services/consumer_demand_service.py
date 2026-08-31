"""
Consumer Demand Intelligence -- 2026-08-31, Company Network cross-industry
expansion #3 (AJ: "由1開始順住做" -- real estate was #1, supply chain was
#2, this closes out the originally-scoped "search trends/consumer"
candidate).

Scoping note, stated honestly up front: this is NOT literal Google
Trends search-volume data. Google Trends has no official, stable,
commercially-licensed API -- the only ways to pull it programmatically
are unofficial scrapers (e.g. pytrends) hitting an undocumented Google
endpoint with no ToS grant for commercial redistribution. That fails
this codebase's already-established bar for what gets built against
(see services/license_registry.py's rejections of bbc_rss pending
verification, reddit_unauthenticated, stocktwits, and oilpriceapi_
baltic_dry_index -- the consistent rule here is "don't build a paid
feature on a data path that isn't verified-legal to redistribute").
Instead this module covers the same underlying question ("is consumer
demand strengthening or weakening") with real, government-published,
public-domain aggregate spending/retail-sales data -- a strictly more
reliable signal than search-interest proxies anyway, at zero legal risk.

Same shape as services/real_estate_service.py and services/
supply_chain_service.py -- national consumer-spending indicators paired
with the specific tickers they're actually relevant to (large retailers,
e-commerce, consumer-discretionary ETFs), never presented as a reading
for an unrelated symbol.

Series chosen (all verified live on FRED, U.S. Census Bureau / BEA
source, "Public Domain: Citation Requested" tag -- deliberately
excluding University of Michigan: Consumer Sentiment (UMCSENT), which
IS on FRED but is marked with a third-party copyright notice requiring
the data owner's permission before non-personal use per FRED's own
terms; see services/license_registry.py's "fred" entry for that rule):
- RSAFS: Advance Retail Sales, Retail Trade and Food Services -- the
  headline monthly retail-spending figure.
- RSXFS: Advance Retail Sales, Retail Trade (excludes food services) --
  the goods-only slice, closer to what a retailer/e-commerce ticker
  actually sells.
- PCE: Personal Consumption Expenditures -- broader than retail alone,
  covers services spending too.
- PCEDG: Personal Consumption Expenditures, Durable Goods -- the most
  cyclical/discretionary slice, most sensitive to demand swings.

Zero new API integration, zero new signup: reuses FRED (services/
fred_macro_service.py already established the dormant-until-FRED_API_KEY
convention and the attribution text this module copies verbatim).
Keeps its own independent _fetch_series()/cache/persistence, per this
codebase's per-collector-module-independence convention (see services/
sec_form4_service.py's module docstring for why) -- NOT a shared import
from fred_macro_service.py, real_estate_service.py, or supply_chain_
service.py.

Honesty contract, same as the rest of this family: FRED's "." (missing
observation) is dropped, never coerced to 0 or interpolated. A ticker not
in _TICKER_TO_NAME below gets `None` from get_consumer_demand_context_
for_ticker(), not a fabricated "no data" reading dressed up as a real one.
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

SOURCE_KEY = "consumer_demand_fred"
register_source(SOURCE_KEY, "FRED US Consumer Spending/Retail", "consumer_demand")

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _init_persistence_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS consumer_demand_observations (
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
            INSERT INTO consumer_demand_observations (series_id, date, value, fetched_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(series_id, date) DO UPDATE SET value=excluded.value, fetched_at=excluded.fetched_at
            """,
            [(series_id, o["date"], o["value"]) for o in observations],
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("consumer_demand_service: failed to persist %s: %s", series_id, e)


def _load_persisted(series_id: str, n_obs: int) -> Optional[list]:
    try:
        conn = sqlite3.connect(_DB_PATH)
        rows = conn.execute(
            "SELECT date, value FROM consumer_demand_observations WHERE series_id=? ORDER BY date DESC LIMIT ?",
            (series_id, n_obs),
        ).fetchall()
        conn.close()
        if not rows:
            return None
        return [{"date": d, "value": v} for d, v in reversed(rows)]
    except Exception:
        return None


_SERIES = {
    "retail_sales_total_musd": {"series_id": "RSAFS", "label": "Advance Retail Sales: Retail Trade and Food Services", "unit": "$ millions"},
    "retail_sales_goods_only_musd": {"series_id": "RSXFS", "label": "Advance Retail Sales: Retail Trade", "unit": "$ millions"},
    "personal_consumption_expenditures_busd": {"series_id": "PCE", "label": "Personal Consumption Expenditures", "unit": "$ billions, SAAR"},
    "durable_goods_consumption_busd": {"series_id": "PCEDG", "label": "Personal Consumption Expenditures: Durable Goods", "unit": "$ billions, SAAR"},
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
        logger.info("consumer_demand_service: failed to fetch %s: %s", series_id, e)
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


# Large retailers, e-commerce, and 2 consumer-discretionary ETFs --
# tickers whose revenue is directly, mechanically exposed to aggregate
# US consumer spending. Deliberately NOT every ticker with "consumer"
# anywhere in its business description -- same conservative-linkage
# reasoning as eia_energy_service.py's USO/UNG-only scope.
_TICKER_TO_NAME = {
    "WMT": "Walmart", "TGT": "Target", "COST": "Costco Wholesale",
    "HD": "The Home Depot", "LOW": "Lowe's Companies", "AMZN": "Amazon.com",
    "BBY": "Best Buy", "TJX": "The TJX Companies", "ROST": "Ross Stores",
    "XRT": "SPDR S&P Retail ETF", "XLY": "Consumer Discretionary Select Sector SPDR Fund",
}


def get_consumer_demand_context_for_ticker(ticker: str) -> Optional[Dict]:
    """Returns {"matched_ticker": "WMT", "matched_name": "Walmart",
    "attribution": "...", "indicators": {series_key: {...} or None}}
    or None if this ticker has no consumer-spending linkage at all
    (never a fabricated reading for an unrelated symbol)."""
    ticker = (ticker or "").upper().strip()
    name = _TICKER_TO_NAME.get(ticker)
    if not name:
        return None
    if not is_available():
        return {"matched_ticker": ticker, "matched_name": name, "available": False,
                "message": f"{FRED_API_KEY_ENV} 未設定，消費數據暫時未開放。"}

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
    print(json.dumps(get_consumer_demand_context_for_ticker("WMT"), indent=2, ensure_ascii=False))
