"""
SEC XBRL Company Facts Service -- 2026-08-28 (AJ: "重有咩要做" -> "咁你一次
過起", picking up the new-source shortlist proposed after the 13D/13G
scheduler shipped).

Why this fills a real gap: every other Data Factory collector so far
covers POSITIONING (13F/13D-13G/COT), EVENT-DRIVEN activity (Form 4
insider trades), or MACRO/COMMODITY context (FRED/Treasury/EIA) -- none
of them carry the company's own actual financial-statement numbers
(revenue, net income, EPS, balance sheet). This is the first genuine
FUNDAMENTALS source in the Data Factory.

Source: SEC's own XBRL Frames/Company Facts API
(data.sec.gov/api/xbrl/companyfacts/CIK##########.json), free, no key,
same SEC_USER_AGENT convention as sec_form4_service.py /
sec_13d_13g_service.py / sec_ownership_service.py. Confirmed reachable
and returns real data for AAPL (CIK 0000320193) during this build.

Each concept (e.g. "Revenues") in the companyfacts payload is a list of
every value the company has EVER reported for that XBRL tag, across every
filing and every fiscal period -- 10-Ks, 10-Qs, restatements, everything.
This module picks the single most recent ANNUAL (form="10-K") value per
concept, so what's surfaced is "latest full fiscal year", not a random or
duplicated quarterly print.

Honesty notes (same posture as every other collector here):
  - Not every company/CIK uses the same XBRL tag for the same concept
    (e.g. some report "Revenues", others "RevenueFromContractWithCustomer
    ExcludingAssessedTax" post-ASC-606 adoption) -- this module tries a
    short list of known-common aliases per concept and uses the first
    one present, rather than guessing or fabricating a number.
  - A concept with zero usable 10-K entries is left out of the response
    entirely (never a fabricated 0 or null placeholder mixed with real
    numbers) -- same "never fabricate a missing value" contract as
    eia_energy_service.py.

2026-09-17 (AJ: "Point-in-time/vintage data質量呢個engineering項目，做啦"):
this module is the pilot integration for services/point_in_time_store.py.
Every successful live fetch now ALSO records each concept's value as an
immutable vintage (keyed by the real SEC "filed" date, not the period
end), alongside the existing overwrite-in-place `sec_xbrl_facts` table
(which is untouched and keeps serving get_company_facts()'s "give me the
current number" use case exactly as before). get_company_facts_as_of()
is the new, additive, point-in-time-correct query for backtesting.
Honesty note: whether SEC's companyfacts payload's "filed" field is
present on every entry was NOT re-verified live from this sandbox this
session (data.sec.gov navigation failed repeatedly) -- it's documented
in SEC's own XBRL API reference as a standard per-fact field, and
_best_annual_value() below treats it as optional (falls back to
recording nothing for vintage purposes, without breaking the existing
live path) if a payload is ever missing it. Watch the first real
production run via the Data Factory admin panel to confirm in practice.
"""
import logging
import os
import sqlite3
from datetime import date, datetime, timezone
from typing import Dict, Optional

from services.outbound_http import get_with_backoff
from services.data_source_registry import (
    register_source, is_source_enabled, record_run_start,
    record_run_success, record_run_error,
)
from services import point_in_time_store as pit

logger = logging.getLogger(__name__)

SEC_USER_AGENT = "XFINLABBot/1.0 (+https://www.xfinlab.com; contact: support@xfinlab.com)"
ATTRIBUTION = "Data sourced from SEC EDGAR XBRL Company Facts (data.sec.gov). Not endorsed or certified by the SEC. For research reference only, not investment advice."

TICKER_CIK_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_TICKER_CIK_CACHE_TTL_DAYS = 7
_ticker_cik_cache = {"data": None, "fetched_at": None}

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"

SOURCE_KEY = "sec_xbrl_facts"
register_source(SOURCE_KEY, "SEC XBRL Company Facts (Fundamentals)", "fundamentals")

# concept_key -> (label, unit, list of XBRL us-gaap tags to try in order)
_CONCEPTS = {
    "revenue": ("Total Revenue", "USD", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]),
    "net_income": ("Net Income", "USD", ["NetIncomeLoss"]),
    "eps_diluted": ("Diluted EPS", "USD/share", ["EarningsPerShareDiluted"]),
    "total_assets": ("Total Assets", "USD", ["Assets"]),
    "total_liabilities": ("Total Liabilities", "USD", ["Liabilities"]),
    "operating_cash_flow": ("Operating Cash Flow", "USD", ["NetCashProvidedByUsedInOperatingActivities"]),
}

_CACHE_TTL_SECONDS = 24 * 3600  # fundamentals only change once a quarter -- no need to refetch more than daily
_cache: Dict[str, Dict] = {}  # ticker -> {"fetched_at": epoch, "facts": {...}, "cik": "..."}

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _init_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sec_xbrl_facts (
            ticker TEXT NOT NULL,
            concept_key TEXT NOT NULL,
            value REAL,
            unit TEXT,
            end_date TEXT,
            form TEXT,
            fetched_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (ticker, concept_key)
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def is_available() -> bool:
    return True  # no API key required -- same as sec_form4_service.py / sec_13d_13g_service.py


def _load_ticker_cik_map() -> dict:
    """Own copy of the ticker->CIK loader -- see sec_form4_service.py's
    module docstring for why each SEC collector keeps its own copy
    instead of sharing one (deliberate decoupling convention across this
    codebase's SEC collectors)."""
    today = date.today()
    cached = _ticker_cik_cache["data"]
    fetched_at = _ticker_cik_cache["fetched_at"]
    if cached and fetched_at and (today - fetched_at).days < _TICKER_CIK_CACHE_TTL_DAYS:
        return cached
    try:
        res = get_with_backoff(TICKER_CIK_MAP_URL, headers={"User-Agent": SEC_USER_AGENT}, timeout=20)
        if res.status_code != 200:
            return cached or {}
        payload = res.json()
        mapping = {str(e["ticker"]).upper(): str(e["cik_str"]) for e in payload.values()}
        _ticker_cik_cache["data"] = mapping
        _ticker_cik_cache["fetched_at"] = today
        return mapping
    except Exception as e:
        logger.info("sec_xbrl_service: failed to load ticker->CIK map: %s", e)
        return cached or {}


def _persist_facts(ticker: str, facts: dict):
    if not facts:
        return
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.executemany(
            """
            INSERT INTO sec_xbrl_facts (ticker, concept_key, value, unit, end_date, form, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(ticker, concept_key) DO UPDATE SET
                value=excluded.value, unit=excluded.unit, end_date=excluded.end_date,
                form=excluded.form, fetched_at=excluded.fetched_at
            """,
            [(ticker, k, v["value"], v["unit"], v["end_date"], v["form"]) for k, v in facts.items()],
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("sec_xbrl_service: failed to persist %s: %s", ticker, e)


def _load_persisted(ticker: str) -> Optional[dict]:
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT concept_key, value, unit, end_date, form FROM sec_xbrl_facts WHERE ticker=?",
            (ticker,),
        ).fetchall()
        conn.close()
        if not rows:
            return None
        return {
            r["concept_key"]: {
                "label": _CONCEPTS.get(r["concept_key"], (r["concept_key"],))[0],
                "value": r["value"], "unit": r["unit"], "end_date": r["end_date"], "form": r["form"],
            }
            for r in rows
        }
    except Exception:
        return None


def _best_annual_value(concept_data: dict) -> Optional[dict]:
    """concept_data is one entry from payload['facts']['us-gaap'][tag]
    (e.g. {"units": {"USD": [ {...}, {...} ]}}). Returns the most recent
    10-K annual datapoint across whichever unit key is present, or None
    if this company has never reported this tag on a 10-K at all.

    Also carries "filed" (SEC's actual filing date for that datapoint)
    through when present, for point_in_time_store.py's benefit -- see
    get_company_facts()'s recording step below. "filed" is optional;
    its absence never affects the existing value/unit/end_date/form
    return contract this function has always had."""
    units = (concept_data or {}).get("units") or {}
    best = None
    for unit_key, entries in units.items():
        for entry in entries:
            if entry.get("form") != "10-K":
                continue
            end_date = entry.get("end")
            val = entry.get("val")
            if end_date is None or val is None:
                continue
            if best is None or end_date > best["end_date"]:
                best = {"value": float(val), "unit": unit_key, "end_date": end_date,
                        "form": "10-K", "filed": entry.get("filed")}
    return best


def get_company_facts(ticker: str) -> Optional[Dict]:
    """
    Returns:
        {"available": True, "ticker": "AAPL", "cik": "0000320193",
         "attribution": "...", "as_of": "...",
         "facts": {"revenue": {"label": "...", "value": ..., "unit": "USD",
                                "end_date": "2025-09-27", "form": "10-K"}, ...}}
        None -- ticker has no CIK match, or every concept came back empty
        (live, cache, AND persisted DB all empty).
    """
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return None

    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(ticker)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return {"available": True, "ticker": ticker, "cik": cached["cik"], "attribution": ATTRIBUTION,
                "as_of": datetime.fromtimestamp(cached["fetched_at"], tz=timezone.utc).isoformat(),
                "facts": cached["facts"]}

    if not is_source_enabled(SOURCE_KEY):
        persisted = _load_persisted(ticker)
        return {"available": True, "ticker": ticker, "cik": None, "attribution": ATTRIBUTION,
                "as_of": None, "facts": persisted} if persisted else None

    cik_map = _load_ticker_cik_map()
    cik = cik_map.get(ticker)
    if not cik:
        persisted = _load_persisted(ticker)
        return {"available": True, "ticker": ticker, "cik": None, "attribution": ATTRIBUTION,
                "as_of": None, "facts": persisted} if persisted else None

    cik10 = cik.zfill(10)
    url = COMPANYFACTS_URL.format(cik10=cik10)
    record_run_start(SOURCE_KEY)
    try:
        res = get_with_backoff(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=20)
        if res.status_code != 200:
            logger.info("sec_xbrl_service: %s (CIK %s) returned HTTP %s", ticker, cik10, res.status_code)
            record_run_error(SOURCE_KEY, f"{ticker} (CIK {cik10}): HTTP {res.status_code}")
            persisted = _load_persisted(ticker)
            return {"available": True, "ticker": ticker, "cik": cik10, "attribution": ATTRIBUTION,
                    "as_of": None, "facts": persisted} if persisted else None
        payload = res.json()
    except Exception as e:
        logger.info("sec_xbrl_service: failed to fetch %s: %s", ticker, e)
        record_run_error(SOURCE_KEY, f"{ticker}: {e}")
        persisted = _load_persisted(ticker)
        return {"available": True, "ticker": ticker, "cik": cik10, "attribution": ATTRIBUTION,
                "as_of": None, "facts": persisted} if persisted else None

    us_gaap = (payload.get("facts") or {}).get("us-gaap") or {}
    facts: Dict[str, dict] = {}
    for concept_key, (label, unit, tags) in _CONCEPTS.items():
        for tag in tags:
            best = _best_annual_value(us_gaap.get(tag))
            if best:
                facts[concept_key] = {"label": label, "value": best["value"], "unit": best["unit"] or unit,
                                       "end_date": best["end_date"], "form": best["form"]}
                filed = best.get("filed")
                if filed:
                    pit.record_observation(
                        source_key=SOURCE_KEY, entity_key=ticker, concept_key=concept_key,
                        value=best["value"], unit=best["unit"] or unit, period_end=best["end_date"],
                        filed_date=filed, form=best["form"],
                    )
                break  # first matching tag alias wins -- never average/merge two different tags

    if facts:
        _cache[ticker] = {"fetched_at": now, "facts": facts, "cik": cik10}
        _persist_facts(ticker, facts)
        record_run_success(SOURCE_KEY)
        return {"available": True, "ticker": ticker, "cik": cik10, "attribution": ATTRIBUTION,
                "as_of": datetime.now(timezone.utc).isoformat(), "facts": facts}

    record_run_error(SOURCE_KEY, f"{ticker} (CIK {cik10}): fetch returned zero usable 10-K concepts")
    persisted = _load_persisted(ticker)
    return {"available": True, "ticker": ticker, "cik": cik10, "attribution": ATTRIBUTION,
            "as_of": None, "facts": persisted} if persisted else None


def get_company_facts_as_of(ticker: str, as_of_date: str) -> Optional[Dict]:
    """Point-in-time-correct sibling of get_company_facts(): for each
    concept, returns whatever was ACTUALLY KNOWN as of as_of_date (i.e.
    already filed and past the availability buffer), never the current/
    latest value. A concept with no qualifying vintage yet by that date
    is simply left out -- exactly like get_company_facts()'s existing
    "never fabricate a missing value" contract, just applied along the
    time axis too.

    Only reads from point_in_time_store's local history -- it never
    makes a live SEC fetch, since "what was known as of a past date"
    cannot be answered by querying SEC's current-state API. A ticker
    needs at least one prior get_company_facts() call (or the daily
    sec_xbrl_refresh job) to have any point-in-time history at all.

    Returns:
        {"available": True, "ticker": "AAPL", "as_of_date": "2024-07-01",
         "attribution": "...", "facts": {"revenue": {...}, ...}}
        {"available": False, ...} -- no PIT history for this ticker as
        of this date (either never ingested, or genuinely nothing was
        knowable yet that early).
    """
    ticker = (ticker or "").upper().strip()
    if not ticker or not as_of_date:
        return None

    facts: Dict[str, dict] = {}
    for concept_key, (label, unit, _tags) in _CONCEPTS.items():
        row = pit.get_latest_value_as_of(SOURCE_KEY, ticker, concept_key, as_of_date)
        if row:
            facts[concept_key] = {
                "label": label, "value": row["value"], "unit": row["unit"] or unit,
                "end_date": row["period_end"], "form": row["form"],
                "filed_date": row["filed_date"], "available_at": row["available_at"],
            }

    if not facts:
        return {"available": False, "ticker": ticker, "as_of_date": as_of_date, "facts": {},
                "message": "No point-in-time history recorded for this ticker as of this date "
                           "-- either it hasn't been ingested yet, or nothing was genuinely "
                           "knowable that early."}

    return {"available": True, "ticker": ticker, "as_of_date": as_of_date,
            "attribution": ATTRIBUTION, "facts": facts,
            "note": "Point-in-time correct: each value reflects only what was actually filed "
                    "and past its availability buffer by as_of_date -- not the latest/current value."}


if __name__ == "__main__":
    import json
    print(json.dumps(get_company_facts("AAPL"), indent=2, ensure_ascii=False))
