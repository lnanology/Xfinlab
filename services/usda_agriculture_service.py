"""
USDA NASS Agricultural Price Service -- 2026-08-28 (AJ: "咁你一次過起";
this slot in the shortlist originally proposed "BLS labor statistics",
swapped after checking fred_macro_service.py -- CPI (CPIAUCSL) and
unemployment (UNRATE) are ALREADY covered there via FRED, so a
dedicated BLS collector would just duplicate an existing source rather
than add anything new. USDA agricultural commodity prices are a genuine
gap instead.

Why this pairs with eia_energy_service.py's own established pattern:
same "positioning vs. fundamentals" idea, applied to agricultural
commodities instead of energy -- CFTC's COT reports already show fund
positioning in corn/wheat/soybean futures, but nothing in the Data
Factory carries the actual physical/fundamental side (USDA's own
official price-received-by-farmers data) the way EIA does for oil/gas.
Pairs with commodity ETF tickers CORN, WEAT, SOYB the same way EIA
pairs with USO/UNG.

Source: USDA NASS ("National Agricultural Statistics Service") Quick
Stats API (quickstats.nass.usda.gov/api), free, official, requires a
free registered API key (quickstats.nass.usda.gov/api -> "Request an
API Key", no cost, no review wait) -- same dormant-until-configured
convention as EIA_API_KEY/FRED_API_KEY. Confirmed request shape via
USDA's own documentation and community client libraries (rnassqs,
usdarnass): key passed as `key=`, JSON returned by default, filtered
via `commodity_desc=`, `short_desc=`, `year__GE=`, `agg_level_desc=`,
`freq_desc=`.

Series chosen -- national, annual, price received by farmers ($/BU),
per USDA's own well-known "CORN, GRAIN - PRICE RECEIVED, MEASURED IN
$/BU" style short_desc convention:
  - CORN, GRAIN - PRICE RECEIVED, MEASURED IN $/BU  (pairs with CORN)
  - WHEAT - PRICE RECEIVED, MEASURED IN $/BU        (pairs with WEAT)
  - SOYBEANS - PRICE RECEIVED, MEASURED IN $/BU     (pairs with SOYB)

Honesty note on short_desc confidence: USDA's short_desc strings are
long, exact-match, and occasionally reorganized between commodities/
years -- same honesty caveat eia_energy_service.py documents for its
own route guesses. A live 200-with-zero-rows or 4xx response is recorded
via record_run_error with the exact short_desc/params that failed
(never silently fabricated), fixable the same one-line way EIA's route
typo was once AJ reports the live admin panel error.
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

USDA_API_KEY_ENV = "USDA_NASS_API_KEY"
USDA_BASE_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
ATTRIBUTION = "Data sourced from the USDA National Agricultural Statistics Service (NASS) Quick Stats API (quickstats.nass.usda.gov). Not endorsed or certified by the USDA."

SOURCE_KEY = "usda_agriculture"
register_source(SOURCE_KEY, "USDA Agricultural Commodity Prices", "agriculture")

# key -> {short_desc, unit, label, commodity_desc, etf_ticker}
_SERIES = {
    "corn_price_received_usd_bu": {
        "short_desc": "CORN, GRAIN - PRICE RECEIVED, MEASURED IN $ / BU",
        "commodity_desc": "CORN", "unit": "$/BU", "label": "Corn -- Price Received by Farmers",
        "etf_ticker": "CORN",
    },
    "wheat_price_received_usd_bu": {
        "short_desc": "WHEAT - PRICE RECEIVED, MEASURED IN $ / BU",
        "commodity_desc": "WHEAT", "unit": "$/BU", "label": "Wheat -- Price Received by Farmers",
        "etf_ticker": "WEAT",
    },
    "soybeans_price_received_usd_bu": {
        "short_desc": "SOYBEANS - PRICE RECEIVED, MEASURED IN $ / BU",
        "commodity_desc": "SOYBEANS", "unit": "$/BU", "label": "Soybeans -- Price Received by Farmers",
        "etf_ticker": "SOYB",
    },
}

_CACHE_TTL_SECONDS = 12 * 3600  # USDA price-received series updates monthly/annually at most
_cache: Dict[str, Dict] = {}  # key -> {"fetched_at": epoch, "period": ..., "value": ...}
_history_cache: Dict[str, Dict] = {}  # key -> {"fetched_at": epoch, "observations": [...]} -- 2026-08-31, see _fetch_history() below

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _init_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usda_agriculture_observations (
            series_key TEXT NOT NULL,
            period TEXT NOT NULL,
            value REAL,
            unit TEXT,
            fetched_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (series_key, period)
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def is_available() -> bool:
    return bool(os.getenv(USDA_API_KEY_ENV))


def _persist(series_key: str, period: str, value: float, unit: str):
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            """
            INSERT INTO usda_agriculture_observations (series_key, period, value, unit, fetched_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(series_key, period) DO UPDATE SET value=excluded.value, unit=excluded.unit, fetched_at=excluded.fetched_at
            """,
            (series_key, period, value, unit),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("usda_agriculture_service: failed to persist %s: %s", series_key, e)


def _load_persisted(series_key: str) -> Optional[dict]:
    try:
        conn = sqlite3.connect(_DB_PATH)
        row = conn.execute(
            "SELECT period, value FROM usda_agriculture_observations WHERE series_key=? ORDER BY period DESC LIMIT 1",
            (series_key,),
        ).fetchone()
        conn.close()
        return {"period": row[0], "value": row[1]} if row else None
    except Exception:
        return None


def _fetch_series(series_key: str) -> Optional[dict]:
    """Returns {"period": "2025", "value": 4.35} for the latest available
    year, or None if live, cache, AND persisted DB all have nothing."""
    meta = _SERIES.get(series_key)
    if not meta:
        return None

    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(series_key)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return {"period": cached["period"], "value": cached["value"]}

    if not is_available() or not is_source_enabled(SOURCE_KEY):
        return {"period": cached["period"], "value": cached["value"]} if cached else _load_persisted(series_key)

    params = {
        "key": os.getenv(USDA_API_KEY_ENV),
        "short_desc": meta["short_desc"],
        "agg_level_desc": "NATIONAL",
        "freq_desc": "ANNUAL",
        "format": "JSON",
    }
    record_run_start(SOURCE_KEY)
    try:
        res = get_with_backoff(USDA_BASE_URL, params=params, timeout=20)
        if res.status_code != 200:
            logger.info("usda_agriculture_service: %s returned HTTP %s", series_key, res.status_code)
            record_run_error(SOURCE_KEY, f"{series_key} ({meta['short_desc']}): HTTP {res.status_code}")
            return {"period": cached["period"], "value": cached["value"]} if cached else _load_persisted(series_key)
        payload = res.json()
    except Exception as e:
        logger.info("usda_agriculture_service: failed to fetch %s: %s", series_key, e)
        record_run_error(SOURCE_KEY, f"{series_key}: {e}")
        return {"period": cached["period"], "value": cached["value"]} if cached else _load_persisted(series_key)

    rows = payload.get("data") or []
    best = None
    for row in rows:
        year = row.get("year")
        raw_value = (row.get("Value") or "").replace(",", "")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue  # genuine missing/withheld observation ("(D)", "(NA)", etc) -- never fabricate a fill-in
        if best is None or (year and year > best["period"]):
            best = {"period": year, "value": value}

    if best:
        _cache[series_key] = {"fetched_at": now, "period": best["period"], "value": best["value"]}
        _persist(series_key, best["period"], best["value"], meta["unit"])
        record_run_success(SOURCE_KEY)
        return best

    record_run_error(SOURCE_KEY, f"{series_key} ({meta['short_desc']}): fetch returned zero usable observations")
    return {"period": cached["period"], "value": cached["value"]} if cached else _load_persisted(series_key)


def _load_persisted_history(series_key: str, n_obs: int) -> Optional[list]:
    try:
        conn = sqlite3.connect(_DB_PATH)
        rows = conn.execute(
            "SELECT period, value FROM usda_agriculture_observations WHERE series_key=? ORDER BY period DESC LIMIT ?",
            (series_key, n_obs),
        ).fetchall()
        conn.close()
        if not rows:
            return None
        return [{"period": p, "value": v} for p, v in reversed(rows)]
    except Exception:
        return None


def _fetch_history(series_key: str, n_obs: int = 6) -> Optional[list]:
    """2026-08-31 (Opportunity Radar expansion): returns up to n_obs most
    recent annual observations, oldest-first, as [{"period": "2021",
    "value": 4.35}, ...] -- unlike _fetch_series() above (which only ever
    surfaces the single latest point, sufficient for get_snapshot()/
    get_agriculture_context_for_ticker()), this exposes a multi-year
    window for trend computation. USDA's own Quick Stats API already
    returns every available year for a given short_desc/agg_level_desc/
    freq_desc combination in one response (no year filter applied here
    or in _fetch_series above) -- so this reuses the exact same request,
    just keeps every year instead of discarding all but the latest.
    Persists every row it sees (not just the latest) into the same
    usda_agriculture_observations table, so repeat calls -- and
    _fetch_series()'s own persisted-fallback -- accumulate real history
    over time too. Same fallback chain (in-memory cache -> persisted
    table -> None) as every other collector here."""
    meta = _SERIES.get(series_key)
    if not meta:
        return None

    now = datetime.now(timezone.utc).timestamp()
    cached = _history_cache.get(series_key)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["observations"]

    if not is_available() or not is_source_enabled(SOURCE_KEY):
        return _load_persisted_history(series_key, n_obs)

    params = {
        "key": os.getenv(USDA_API_KEY_ENV),
        "short_desc": meta["short_desc"],
        "agg_level_desc": "NATIONAL",
        "freq_desc": "ANNUAL",
        "format": "JSON",
    }
    record_run_start(SOURCE_KEY)
    try:
        res = get_with_backoff(USDA_BASE_URL, params=params, timeout=20)
        if res.status_code != 200:
            logger.info("usda_agriculture_service: %s history returned HTTP %s", series_key, res.status_code)
            record_run_error(SOURCE_KEY, f"{series_key} ({meta['short_desc']}) history: HTTP {res.status_code}")
            return _load_persisted_history(series_key, n_obs)
        payload = res.json()
    except Exception as e:
        logger.info("usda_agriculture_service: failed to fetch %s history: %s", series_key, e)
        record_run_error(SOURCE_KEY, f"{series_key} history: {e}")
        return _load_persisted_history(series_key, n_obs)

    rows = payload.get("data") or []
    by_year: Dict[str, float] = {}
    for row in rows:
        year = row.get("year")
        raw_value = (row.get("Value") or "").replace(",", "")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue  # genuine missing/withheld observation ("(D)", "(NA)", etc) -- never fabricate a fill-in
        if not year:
            continue
        by_year[year] = value

    if not by_year:
        record_run_error(SOURCE_KEY, f"{series_key} ({meta['short_desc']}) history: fetch returned zero usable observations")
        return _load_persisted_history(series_key, n_obs)

    for year, value in by_year.items():
        _persist(series_key, year, value, meta["unit"])
    record_run_success(SOURCE_KEY)

    observations = [{"period": y, "value": v} for y, v in sorted(by_year.items())][-n_obs:]
    _history_cache[series_key] = {"fetched_at": now, "observations": observations}
    return observations


def get_snapshot() -> Dict:
    """
    Returns:
        {"available": True, "as_of": "...", "attribution": "...",
         "series": {"corn_price_received_usd_bu": {"label": "...",
             "unit": "$/BU", "period": "2025", "value": 4.35,
             "etf_ticker": "CORN"}, ...}}
        {"available": False, "message": "..."} -- USDA_NASS_API_KEY not
        configured, or every series failed (live, cache, AND persisted
        DB all empty).
    """
    if not is_available():
        return {"available": False, "message": f"{USDA_API_KEY_ENV} 未設定，USDA農產品數據暫時未開放。"}

    series: Dict[str, Optional[dict]] = {}
    for key, meta in _SERIES.items():
        obs = _fetch_series(key)
        series[key] = (
            {"label": meta["label"], "unit": meta["unit"], "period": obs["period"], "value": obs["value"],
             "etf_ticker": meta["etf_ticker"]}
            if obs else None
        )

    if all(v is None for v in series.values()):
        return {"available": False, "message": "USDA暫時未能提供任何農產品數據（可能係首次運行或短暫故障）。"}

    return {"available": True, "as_of": datetime.now(timezone.utc).isoformat(),
            "attribution": ATTRIBUTION, "series": series}


_TICKER_TO_SERIES = {meta["etf_ticker"]: key for key, meta in _SERIES.items()}


def get_agriculture_context_for_ticker(ticker: str) -> Optional[Dict]:
    """Returns {"matched_ticker": "CORN", "attribution": "...",
    "series": {...}} or None if this ticker has no USDA-relevant mapping
    at all -- same convention as eia_energy_service.get_energy_context_for_ticker()."""
    series_key = _TICKER_TO_SERIES.get((ticker or "").upper().strip())
    if not series_key:
        return None
    meta = _SERIES[series_key]
    obs = _fetch_series(series_key)
    if not obs:
        return None
    return {"matched_ticker": ticker.upper(), "attribution": ATTRIBUTION,
            "series": {series_key: {"label": meta["label"], "unit": meta["unit"],
                                     "period": obs["period"], "value": obs["value"]}}}


if __name__ == "__main__":
    import json
    print(json.dumps(get_snapshot(), indent=2, ensure_ascii=False))
