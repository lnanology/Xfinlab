"""
US Treasury Fiscal Data Service -- 2026-08-27, Data Factory Step 8b
(AJ: "一次過全加可以嗎" -- add EIA + Treasury + Coinbase together).

What this adds that services/fred_macro_service.py doesn't already
cover: FRED's series are the Fed's economic/monetary view (rates,
inflation, unemployment, Fed balance sheet, RRP). This module is the
FISCAL side -- the federal government's own debt and cash position,
published directly by the U.S. Treasury (not derived/re-hosted by the
Fed). "How much does the government owe, and how much cash does it
actually have sitting in its own checking account (the TGA)" is a
genuinely different upstream driver of liquidity than the Fed's balance
sheet -- a falling TGA balance means the Treasury is spending down cash
into the economy (a liquidity tailwind for markets), independent of
whatever the Fed itself is doing. This is a distinct data type, not a
duplicate of get_liquidity_snapshot().

Source: U.S. Treasury's own Fiscal Data API (api.fiscaldata.treasury.gov),
confirmed via fiscaldata.treasury.gov/api-documentation/ -- public,
free, NO API key required at all (unlike FRED/EIA). Response envelope is
{"data": [...], "meta": {...}, "links": {...}}; all data values are
returned as strings, filtering via `filter=field:eq:value`, field
selection via `fields=`, sorting via `sort=-field` (descending), and
`page[size]=`/`page[number]=` for pagination.

Two datasets used (endpoint paths + field names confirmed against
Treasury's own dataset pages, same confidence level as EIA's spot-price
series -- if a field name has drifted, a live fetch surfaces a clean
HTTP/parse failure via record_run_error rather than a fabricated value):
  - v2/accounting/od/debt_to_penny -- fields record_date,
    tot_pub_debt_out_amt (total public debt outstanding, USD, daily,
    updated end of each business day).
  - v1/accounting/dts/operating_cash_balance -- filtered to
    account_type "Treasury General Account (TGA) Closing Balance",
    field close_today_bal (millions of USD, daily on business days).

Same self-registering + cache + SQLite-persistence pattern as every
other Data Factory collector.
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

TREASURY_BASE_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
ATTRIBUTION = "Data sourced from the U.S. Treasury Fiscal Data API (fiscaldata.treasury.gov). Not endorsed or certified by the U.S. Treasury."

SOURCE_KEY = "treasury_fiscal"
register_source(SOURCE_KEY, "US Treasury Fiscal Data", "fiscal")

_SERIES = {
    "total_public_debt_usd": {
        "path": "v2/accounting/od/debt_to_penny",
        "date_field": "record_date", "value_field": "tot_pub_debt_out_amt",
        "extra_filter": None,
        "unit": "USD", "label": "Total Public Debt Outstanding",
    },
    "treasury_general_account_balance_usd_millions": {
        "path": "v1/accounting/dts/operating_cash_balance",
        "date_field": "record_date", "value_field": "close_today_bal",
        "extra_filter": "account_type:eq:Treasury General Account (TGA) Closing Balance",
        "unit": "USD millions", "label": "Treasury General Account (TGA) Closing Balance",
    },
}

_CACHE_TTL_SECONDS = 6 * 3600  # both series update once per business day
_cache: Dict[str, Dict] = {}  # key -> {"fetched_at": epoch, "observations": [...]}

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _init_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS treasury_fiscal_observations (
            series_key TEXT NOT NULL,
            record_date TEXT NOT NULL,
            value REAL,
            unit TEXT,
            fetched_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (series_key, record_date)
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def _to_float(raw) -> Optional[float]:
    if raw in (None, "", "null"):
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
            INSERT INTO treasury_fiscal_observations (series_key, record_date, value, unit, fetched_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(series_key, record_date) DO UPDATE SET value=excluded.value, unit=excluded.unit, fetched_at=excluded.fetched_at
            """,
            [(series_key, o["record_date"], o["value"], unit) for o in observations],
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("treasury_fiscal_service: failed to persist %s: %s", series_key, e)


def _load_persisted(series_key: str, n_obs: int) -> Optional[list]:
    try:
        conn = sqlite3.connect(_DB_PATH)
        rows = conn.execute(
            "SELECT record_date, value FROM treasury_fiscal_observations WHERE series_key=? ORDER BY record_date DESC LIMIT ?",
            (series_key, n_obs),
        ).fetchall()
        conn.close()
        if not rows:
            return None
        return [{"record_date": d, "value": v} for d, v in reversed(rows)]
    except Exception:
        return None


def _fetch_series(series_key: str, n_obs: int = 30) -> Optional[list]:
    """Returns up to n_obs most recent observations, oldest-first, as
    [{"record_date": "2026-08-25", "value": 36000000000000.0}, ...].
    None if no live, cached, or persisted data at all. Same fallback
    order as every other collector: in-memory cache -> SQLite -> None."""
    meta = _SERIES.get(series_key)
    if not meta:
        return None

    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(series_key)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["observations"]

    if not is_source_enabled(SOURCE_KEY):
        return (cached["observations"] if cached else None) or _load_persisted(series_key, n_obs)

    url = f"{TREASURY_BASE_URL}/{meta['path']}"
    params = {
        "fields": f"{meta['date_field']},{meta['value_field']}",
        "sort": f"-{meta['date_field']}",
        "page[size]": n_obs,
    }
    if meta["extra_filter"]:
        params["filter"] = meta["extra_filter"]

    record_run_start(SOURCE_KEY)
    try:
        res = get_with_backoff(url, params=params, timeout=15)
        if res.status_code != 200:
            logger.info("treasury_fiscal_service: %s returned HTTP %s", series_key, res.status_code)
            record_run_error(SOURCE_KEY, f"{series_key} ({meta['path']}): HTTP {res.status_code}")
            return (cached["observations"] if cached else None) or _load_persisted(series_key, n_obs)
        payload = res.json()
    except Exception as e:
        logger.info("treasury_fiscal_service: failed to fetch %s: %s", series_key, e)
        record_run_error(SOURCE_KEY, f"{series_key}: {e}")
        return (cached["observations"] if cached else None) or _load_persisted(series_key, n_obs)

    rows = payload.get("data") or []
    observations = []
    for row in reversed(rows):  # API gave newest-first (sort desc); store oldest-first
        value = _to_float(row.get(meta["value_field"]))
        record_date = row.get(meta["date_field"])
        if value is None or not record_date:
            continue  # genuine missing observation -- never fabricate a fill-in
        observations.append({"record_date": record_date, "value": value})

    if observations:
        _cache[series_key] = {"fetched_at": now, "observations": observations}
        _persist_observations(series_key, meta["unit"], observations)
        record_run_success(SOURCE_KEY)
        return observations
    record_run_error(SOURCE_KEY, f"{series_key} ({meta['path']}): fetch returned zero usable observations")
    return (cached["observations"] if cached else None) or _load_persisted(series_key, n_obs)


def get_snapshot() -> Dict:
    """
    Returns:
        {"available": True, "as_of": "...", "attribution": "...",
         "series": {
            "total_public_debt_usd": {"label": "...", "unit": "USD",
                "record_date": "2026-08-25", "value": 36...,
                "period_change_pct": 0.03},
            "treasury_general_account_balance_usd_millions": {..., "period_change_pct": -4.1},
         }}
        {"available": False, "message": "..."} if every series fetch
        failed (live, cache, AND persisted DB all empty -- e.g. very
        first run ever).

    period_change_pct compares the latest observation against the
    oldest one in the ~30-observation window fetched -- a rough ~1-month
    trend direction, not a fixed calendar period (Treasury doesn't
    publish on weekends/holidays so exact day-count varies slightly).
    """
    series: Dict[str, Optional[dict]] = {}
    for key, meta in _SERIES.items():
        obs = _fetch_series(key, n_obs=30)
        if obs:
            latest = obs[-1]
            period_change_pct = None
            if len(obs) >= 2 and obs[0]["value"]:
                period_change_pct = round((latest["value"] - obs[0]["value"]) / abs(obs[0]["value"]) * 100, 3)
            series[key] = {
                "label": meta["label"], "unit": meta["unit"],
                "record_date": latest["record_date"], "value": latest["value"],
                "period_change_pct": period_change_pct,
            }
        else:
            series[key] = None

    if all(v is None for v in series.values()):
        return {"available": False, "message": "美國財政部數據暫時未能提供（可能係首次運行或短暫故障）。"}

    return {
        "available": True,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "attribution": ATTRIBUTION,
        "series": series,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_snapshot(), indent=2, ensure_ascii=False))
