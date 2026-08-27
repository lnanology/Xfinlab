"""
EIA (U.S. Energy Information Administration) Energy Data Service --
2026-08-27, Data Factory Step 8a (AJ: "一次過全加可以嗎" -- add EIA +
Treasury + Coinbase together after Binance shipped clean).

Why this pairs with services/cftc_cot_service.py rather than duplicating
it: CFTC's WTI Crude Oil (067651) and Natural Gas (023651) COT contracts
already show how big speculators/hedgers are POSITIONED in these
markets, but positioning alone never says whether that positioning
matches physical reality. EIA is the US government's own energy-supply
statistics agency -- actual spot prices and actual inventory levels.
Read together: "funds are net long crude AND inventories are drawing
down" is a very different picture from "funds are net long crude WHILE
inventories are building" -- the gap between positioning and
fundamentals is the genuinely new signal this adds, not a duplicate of
either existing data source.

Source: EIA's own API v2 (api.eia.gov/v2), free, official, requires a
free registered API key (eia.gov/opendata/register/, no cost, no review
wait -- same dormant-until-configured convention as FRED_API_KEY in
services/fred_macro_service.py). Confirmed via EIA's own v2 API
documentation (eia.gov/opendata/documentation.php): key passed as a URL
query param `api_key=`, JSON envelope is {"response": {"data": [...],
"total": ..., ...}, "request": {...}, "apiVersion": ...}, value columns
selected via `data[0]=value`, series filtered via `facets[series][]=`,
ordering via `sort[0][column]=period&sort[0][direction]=desc`. All
returned data values are strings (per EIA's own v2.1.6 changelog) --
this module coerces defensively, same "never fabricate a missing value"
contract as every other collector here.

Series chosen (route + series ID confirmed against EIA's public data
browser / DNAV pages, not guessed blind):
  - petroleum/pri/spt, series RWTC: Cushing, OK WTI Spot Price FOB
    ($/BBL, daily) -- pairs with CFTC contract 067651.
  - natural-gas/pri/sum, series RNGWHHD: Henry Hub Natural Gas Spot
    Price ($/MMBTU, daily) -- pairs with CFTC contract 023651.
  - natural-gas/stor/wkly, series NW2_EPG0_SWO_R48_BCF: Lower-48 states
    working natural gas in underground storage (BCF, weekly) -- the
    inventory-fundamentals side with no COT equivalent at all.

Honesty note on route confidence: the petroleum/gas SPOT PRICE routes
above are the same well-known series EIA publishes on its own DNAV
pages, high confidence. If EIA has since reorganized a route (their v2
hierarchy has shifted before), a live fetch will surface a clean
HTTP 4xx recorded via record_run_error with the exact route+series
that failed -- never silently fabricated -- and can be corrected the
same way the CFTC field-typo and SEC 13F infotable-detection bugs were:
AJ reports the live admin panel error, this module gets a one-line fix.

Same self-registering + cache + SQLite-persistence pattern as every
other Data Factory collector (see services/data_source_registry.py).
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

EIA_API_KEY_ENV = "EIA_API_KEY"
EIA_BASE_URL = "https://api.eia.gov/v2"
ATTRIBUTION = "Data sourced from the U.S. Energy Information Administration (EIA) Open Data API (api.eia.gov). Not endorsed or certified by the EIA."

SOURCE_KEY = "eia_energy"
register_source(SOURCE_KEY, "EIA Energy Prices & Storage", "energy")

# key -> {route, series_id, frequency, unit, label, cot_contract_code}
# cot_contract_code cross-references services/cftc_cot_service.py's
# _CONTRACTS so a caller can show "positioning vs fundamentals" side by
# side without this module importing that one (kept decoupled -- the
# pairing is documentation/convention, not a code dependency).
_SERIES = {
    "wti_crude_spot_usd_bbl": {
        "route": "petroleum/pri/spt", "series_id": "RWTC", "frequency": "daily",
        "unit": "$/BBL", "label": "WTI Crude Oil Spot Price (Cushing, OK)",
        "cot_contract_code": "067651",
    },
    "henry_hub_natgas_spot_usd_mmbtu": {
        # 2026-08-27: two-round live fix. Round 1 guessed route
        # "natural-gas/pri/sum" with frequency="daily", which failed
        # with "Invalid frequency 'daily' provided. The only valid
        # frequencies are 'monthly', and 'annual'." Switching that same
        # WRONG route to frequency="monthly" then returned HTTP 200 but
        # zero rows for facets[series][]=RNGWHHD -- meaning "sum" was
        # never the right route for this series at all (its frequency
        # error was a red herring). Confirmed correct route via
        # gridstatus's open-source EIA v2 wrapper (github.com/
        # gridstatus/gridstatus, eia.py), whose own
        # HENRY_HUB_NATURAL_GAS_SPOT_PRICES_PATH constant is
        # "natural-gas/pri/fut" (EIA's "Daily Spot and Futures Prices
        # for select petroleum products, natural gas, and biofuels"
        # report -- despite the "fut" in the path, this route also
        # carries Henry Hub's own SPOT price series, RNGWHHD, alongside
        # actual futures contracts for other products). Their wrapper
        # calls this route with frequency="daily", confirming daily
        # was never invalid for the RIGHT route.
        "route": "natural-gas/pri/fut", "series_id": "RNGWHHD", "frequency": "daily",
        "unit": "$/MMBTU", "label": "Henry Hub Natural Gas Spot Price",
        "cot_contract_code": "023651",
    },
    "natgas_storage_lower48_bcf": {
        "route": "natural-gas/stor/wkly", "series_id": "NW2_EPG0_SWO_R48_BCF", "frequency": "weekly",
        "unit": "BCF", "label": "Working Natural Gas in Underground Storage (Lower 48)",
        "cot_contract_code": "023651",
    },
}

_CACHE_TTL_SECONDS = 6 * 3600  # daily/weekly series -- no need to re-hit EIA more often than this
_cache: Dict[str, Dict] = {}  # key -> {"fetched_at": epoch, "observations": [...]}

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _init_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS eia_energy_observations (
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
    return bool(os.getenv(EIA_API_KEY_ENV))


def _to_float(raw) -> Optional[float]:
    if raw in (None, "", "NA", "W"):  # EIA uses "NA"/"W" (withheld) as well as blank for missing
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _persist_observations(series_key: str, unit: str, observations: list):
    if not observations:
        return
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.executemany(
            """
            INSERT INTO eia_energy_observations (series_key, period, value, unit, fetched_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(series_key, period) DO UPDATE SET value=excluded.value, unit=excluded.unit, fetched_at=excluded.fetched_at
            """,
            [(series_key, o["period"], o["value"], unit) for o in observations],
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("eia_energy_service: failed to persist %s: %s", series_key, e)


def _load_persisted(series_key: str, n_obs: int) -> Optional[list]:
    try:
        conn = sqlite3.connect(_DB_PATH)
        rows = conn.execute(
            "SELECT period, value FROM eia_energy_observations WHERE series_key=? ORDER BY period DESC LIMIT ?",
            (series_key, n_obs),
        ).fetchall()
        conn.close()
        if not rows:
            return None
        return [{"period": p, "value": v} for p, v in reversed(rows)]
    except Exception:
        return None


def _fetch_series(series_key: str, n_obs: int = 8) -> Optional[list]:
    """Returns up to n_obs most recent observations, oldest-first, as
    [{"period": "2026-08-25", "value": 63.55}, ...]. None if no live,
    cached, or persisted data at all. Fallback order: in-memory cache ->
    eia_energy_observations table -> None -- same convention as
    fred_macro_service.py's _fetch_series."""
    meta = _SERIES.get(series_key)
    if not meta:
        return None

    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(series_key)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["observations"]

    if not is_available():
        return (cached["observations"] if cached else None) or _load_persisted(series_key, n_obs)

    if not is_source_enabled(SOURCE_KEY):
        return (cached["observations"] if cached else None) or _load_persisted(series_key, n_obs)

    url = f"{EIA_BASE_URL}/{meta['route']}/data/"
    params = {
        "api_key": os.getenv(EIA_API_KEY_ENV),
        "frequency": meta["frequency"],
        "data[0]": "value",
        "facets[series][]": meta["series_id"],
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "offset": 0,
        "length": n_obs,
    }
    record_run_start(SOURCE_KEY)
    try:
        res = get_with_backoff(url, params=params, timeout=15)
        if res.status_code != 200:
            logger.info("eia_energy_service: %s (%s) returned HTTP %s", series_key, meta["route"], res.status_code)
            record_run_error(SOURCE_KEY, f"{series_key} ({meta['route']}/{meta['series_id']}): HTTP {res.status_code}")
            return (cached["observations"] if cached else None) or _load_persisted(series_key, n_obs)
        payload = res.json()
    except Exception as e:
        logger.info("eia_energy_service: failed to fetch %s: %s", series_key, e)
        record_run_error(SOURCE_KEY, f"{series_key}: {e}")
        return (cached["observations"] if cached else None) or _load_persisted(series_key, n_obs)

    rows = (payload.get("response") or {}).get("data") or []
    observations = []
    for row in reversed(rows):  # EIA gives newest-first (sort desc); store oldest-first
        value = _to_float(row.get("value"))
        period = row.get("period")
        if value is None or not period:
            continue  # genuine missing/withheld observation -- never fabricate a fill-in
        observations.append({"period": period, "value": value})

    if observations:
        _cache[series_key] = {"fetched_at": now, "observations": observations}
        _persist_observations(series_key, meta["unit"], observations)
        record_run_success(SOURCE_KEY)
        return observations
    record_run_error(SOURCE_KEY, f"{series_key} ({meta['route']}/{meta['series_id']}): fetch returned zero usable observations")
    return (cached["observations"] if cached else None) or _load_persisted(series_key, n_obs)


def get_snapshot() -> Dict:
    """
    Returns:
        {"available": True, "as_of": "...", "attribution": "...",
         "series": {
            "wti_crude_spot_usd_bbl": {"label": "...", "unit": "$/BBL",
                "period": "2026-08-25", "value": 63.55, "cot_contract_code": "067651"},
            ...
         }}
        {"available": False, "message": "..."} -- EIA_API_KEY not
        configured, or every series failed (live, cache, AND persisted
        DB all empty).
    """
    if not is_available():
        return {"available": False, "message": f"{EIA_API_KEY_ENV} 未設定，EIA能源數據暫時未開放。"}

    series: Dict[str, Optional[dict]] = {}
    for key, meta in _SERIES.items():
        obs = _fetch_series(key, n_obs=8)
        if obs:
            latest = obs[-1]
            series[key] = {
                "label": meta["label"], "unit": meta["unit"],
                "period": latest["period"], "value": latest["value"],
                "cot_contract_code": meta["cot_contract_code"],
            }
        else:
            series[key] = None

    if all(v is None for v in series.values()):
        return {"available": False, "message": "EIA暫時未能提供任何能源數據（可能係首次運行或短暫故障）。"}

    return {
        "available": True,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "attribution": ATTRIBUTION,
        "series": series,
    }


def get_series_history(series_key: str, n_obs: int = 8) -> Optional[list]:
    """Small history window (default 8 points) for a single series --
    e.g. for a caller that wants to show a short trend, not just the
    latest print."""
    if series_key not in _SERIES:
        return None
    return _fetch_series(series_key, n_obs=n_obs)


# ---------------------------------------------------------------------------
# Ticker pairing, mirroring services/cftc_cot_service.py's
# get_cot_for_ticker() -- same rationale: only a small explicit set of
# tickers genuinely track something EIA measures (USO -> WTI, UNG ->
# Henry Hub/storage). Anything not in this table returns None rather
# than a guessed/misleading match.
# ---------------------------------------------------------------------------
_TICKER_TO_SERIES = {
    "USO": ["wti_crude_spot_usd_bbl"],
    "UNG": ["henry_hub_natgas_spot_usd_mmbtu", "natgas_storage_lower48_bcf"],
}


def get_energy_context_for_ticker(ticker: str) -> Optional[Dict]:
    """Returns {"matched_ticker": "USO", "attribution": "...",
    "series": {series_key: {...} or None}} or None if this ticker has no
    EIA-relevant mapping at all."""
    keys = _TICKER_TO_SERIES.get((ticker or "").upper().strip())
    if not keys:
        return None
    out = {}
    for key in keys:
        meta = _SERIES[key]
        obs = _fetch_series(key, n_obs=1)
        out[key] = (
            {"label": meta["label"], "unit": meta["unit"], "period": obs[-1]["period"], "value": obs[-1]["value"]}
            if obs else None
        )
    if all(v is None for v in out.values()):
        return None
    return {"matched_ticker": ticker.upper(), "attribution": ATTRIBUTION, "series": out}


if __name__ == "__main__":
    import json
    print(json.dumps(get_snapshot(), indent=2, ensure_ascii=False))
