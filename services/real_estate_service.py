"""
Real Estate / Housing-Fundamentals Context -- 2026-08-30, Company Network
Phase 4 follow-up (AJ: cross-industry expansion, picked "地產" as the
first of three candidate industries, "由1開始順住做" -- start with #1,
work through the others after).

What this is: same shape as services/eia_energy_service.py (WTI/Henry Hub
-> USO/UNG) and services/usda_agriculture_service.py (corn/wheat/soybean
-> CORN/WEAT/SOYB) -- national housing-market indicators paired with the
specific tickers they're actually relevant to (homebuilders, REITs, a
housing-sector ETF), never presented as a reading for an unrelated
symbol.

Zero new API integration, zero new signup: reuses FRED (services/
fred_macro_service.py already established the dormant-until-FRED_API_KEY
convention and the attribution text this module copies verbatim; FRED_API_KEY
was already confirmed set on Railway back when that module shipped).
Keeps its own independent _fetch_series()/cache/persistence, same
deliberate per-module-independence convention every other collector in
this codebase follows (see services/sec_form4_service.py's module
docstring for why) -- NOT a shared import from fred_macro_service.py,
whose _SERIES/_cache are scoped to a different indicator set.

Honesty contract, same as fred_macro_service.py: FRED's "." (missing
observation) is dropped, never coerced to 0 or interpolated. A ticker not
in _TICKER_TO_NAME below gets `None` from get_real_estate_context_for_
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

SOURCE_KEY = "real_estate_fred"
register_source(SOURCE_KEY, "FRED US Housing/Real Estate", "real_estate")

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _init_persistence_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS real_estate_observations (
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
            INSERT INTO real_estate_observations (series_id, date, value, fetched_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(series_id, date) DO UPDATE SET value=excluded.value, fetched_at=excluded.fetched_at
            """,
            [(series_id, o["date"], o["value"]) for o in observations],
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("real_estate_service: failed to persist %s: %s", series_id, e)


def _load_persisted(series_id: str, n_obs: int) -> Optional[list]:
    try:
        conn = sqlite3.connect(_DB_PATH)
        rows = conn.execute(
            "SELECT date, value FROM real_estate_observations WHERE series_id=? ORDER BY date DESC LIMIT ?",
            (series_id, n_obs),
        ).fetchall()
        conn.close()
        if not rows:
            return None
        return [{"date": d, "value": v} for d, v in reversed(rows)]
    except Exception:
        return None


# Series chosen for real, direct relevance to housing-linked tickers and
# genuine FRED public availability (no "Copyright"-marked series -- see
# services/license_registry.py's fred entry).
_SERIES = {
    "mortgage_rate_30y_pct": {"series_id": "MORTGAGE30US", "label": "30-Year Fixed Mortgage Rate", "unit": "%"},
    "home_price_index": {"series_id": "CSUSHPINSA", "label": "S&P/Case-Shiller U.S. National Home Price Index", "unit": "index (Jan 2000=100)"},
    "housing_starts_thousands": {"series_id": "HOUST", "label": "Housing Starts (new privately-owned units)", "unit": "thousand units, SAAR"},
    "existing_home_sales_thousands": {"series_id": "EXHOSLUSM495S", "label": "Existing Home Sales", "unit": "thousand units, SAAR"},
}

_CACHE_TTL_SECONDS = 6 * 3600
_cache: Dict[str, Dict] = {}


def is_available() -> bool:
    return bool(os.getenv(FRED_API_KEY_ENV))


def _fetch_series(series_id: str, n_obs: int = 1) -> Optional[list]:
    """Returns up to n_obs most recent observations, oldest-first. Same
    in-memory-cache -> persisted-table -> None fallback chain as
    fred_macro_service.py's _fetch_series (see that module for the full
    reasoning); kept as an independent copy here per this codebase's
    per-collector-module-independence convention."""
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
        logger.info("real_estate_service: failed to fetch %s: %s", series_id, e)
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


# Homebuilders, REITs, a mortgage originator, and 3 housing-sector ETFs --
# tickers with a real, direct housing-market link. Deliberately NOT every
# ticker with "real estate" anywhere in its business description (e.g.
# generic diversified conglomerates) -- same conservative-linkage
# reasoning as eia_energy_service.py's USO/UNG-only scope.
_TICKER_TO_NAME = {
    "DHI": "D.R. Horton", "LEN": "Lennar", "PHM": "PulteGroup", "NVR": "NVR Inc",
    "TOL": "Toll Brothers", "KBH": "KB Home", "MTH": "Meritage Homes",
    "O": "Realty Income", "SPG": "Simon Property Group", "PLD": "Prologis",
    "PSA": "Public Storage", "AVB": "AvalonBay Communities", "EQR": "Equity Residential",
    "RKT": "Rocket Companies",
    "VNQ": "Vanguard Real Estate ETF", "XHB": "SPDR S&P Homebuilders ETF", "ITB": "iShares U.S. Home Construction ETF",
}


def get_real_estate_context_for_ticker(ticker: str) -> Optional[Dict]:
    """Returns {"matched_ticker": "DHI", "matched_name": "D.R. Horton",
    "attribution": "...", "indicators": {series_key: {...} or None}}
    or None if this ticker has no housing-market linkage at all (never a
    fabricated reading for an unrelated symbol)."""
    ticker = (ticker or "").upper().strip()
    name = _TICKER_TO_NAME.get(ticker)
    if not name:
        return None
    if not is_available():
        return {"matched_ticker": ticker, "matched_name": name, "available": False,
                "message": f"{FRED_API_KEY_ENV} 未設定，地產數據暫時未開放。"}

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
    print(json.dumps(get_real_estate_context_for_ticker("DHI"), indent=2, ensure_ascii=False))
