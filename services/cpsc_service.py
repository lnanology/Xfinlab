"""
CPSC Consumer Product Recalls -- 2026-08-31 (AJ: "感官與消費者科學"
follow-up, picked alongside services/openfda_service.py; see that
module's docstring for why USDA ERS "Food Dollar" was rejected instead).

What this is: U.S. Consumer Product Safety Commission recall records,
per-ticker via an explicit manufacturer-keyword map, broader than
openFDA's FDA-regulated scope (food/drug/device/cosmetics) -- CPSC
covers general consumer products (toys, appliances, furniture,
electronics, tools). Same event-driven shape as openfda_service.py and
services/sec_13d_13g_service.py -- a recent window, not a "current
value".

Source: CPSC's own "Recall Retrieval Web Services" REST API
(saferproducts.gov/RestWebServices/Recall), documented in CPSC's public
Programmer's Guide (cpsc.gov/Recalls/CPSC-Recalls-Application-Program-
Interface-API-Information). No API key or signup required. Query by
`Manufacturer=<term>` (case-insensitive wildcard match per CPSC's own
docs), `RecallDateStart=`/`RecallDateEnd=` for the date window,
`format=json`. Response shape verified directly against the
Programmer's Guide (Version 1.3, Oct 2017): top-level RecallID/
RecallNumber/RecallDate/Description/URL/Title/ConsumerContact/
LastPublishDate, plus Products[{Name,...}], Manufacturers[{Name,
CompanyID}], Hazards[{Name,...}], Remedies[{Name}] collections.

Honesty note on live reliability, as of 2026-08-31: this module's own
verification queries against the live saferproducts.gov endpoint
(several different search shapes, all per the documented examples)
consistently returned a real API-level error --
`{"Title":"Error retrieving Recalls: The underlying provider failed on
Open.", ...}` -- rather than the field-shaped recall data itself. This
reads as a genuine intermittent outage on CPSC's own backend (a known,
documented issue with this legacy API elsewhere), not a request-shape
mistake on our end -- the query parameters and response schema above
are taken directly from CPSC's own published documentation, not
guessed. This module is written to degrade the same way every other
Data Factory collector does (persisted-fallback -> honest empty), so it
starts working automatically whenever CPSC's own service recovers; no
code change will be needed. If it stays down for an extended period,
that's worth flagging back to CPSC or reconsidering this source, not
silently working around with fabricated data.
"""
import logging
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from services.outbound_http import get_with_backoff
from services.data_source_registry import (
    register_source, is_source_enabled, record_run_start,
    record_run_success, record_run_error,
)

logger = logging.getLogger(__name__)

CPSC_BASE_URL = "https://www.saferproducts.gov/RestWebServices/Recall"
ATTRIBUTION = (
    "Data sourced from the U.S. Consumer Product Safety Commission's Recall Retrieval Web Services "
    "(saferproducts.gov). Not an endorsement or official CPSC communication."
)

SOURCE_KEY = "cpsc_recalls"
register_source(SOURCE_KEY, "CPSC Consumer Product Recalls", "consumer_safety")

_LOOKBACK_DAYS = 365  # same window as openfda_service.py, same reasoning

# ticker -> manufacturer-name keywords tried against CPSC's own
# case-insensitive wildcard Manufacturer= search. Deliberately explicit
# -- a ticker not listed here gets None, never a guessed match. Overlaps
# intentionally with openfda_service.py's food/drug/device brands where
# a company also makes general consumer products (e.g. PG, CHD).
_TICKER_TO_KEYWORDS = {
    "PG": ["Procter & Gamble", "Procter and Gamble"],
    "CHD": ["Church & Dwight"],
    "CLX": ["Clorox"],
    "KMB": ["Kimberly-Clark", "Kimberly Clark"],
    "NWL": ["Newell Brands", "Newell", "Rubbermaid", "Graco", "Coleman"],
    "HAS": ["Hasbro"],
    "MAT": ["Mattel"],
    "WHR": ["Whirlpool"],
    "HELE": ["Helen of Troy"],
    "SNA": ["Snap-on"],
    "SWK": ["Stanley Black & Decker", "Stanley Black and Decker", "Black & Decker", "DeWalt"],
    "TTI": ["Techtronic Industries", "Milwaukee Tool", "Ryobi"],
    "GE": ["General Electric", "GE Appliances"],
    "GPK": ["Graphic Packaging"],
    "GT": ["Goodyear Tire"],
    "TPX": ["Tempur Sealy", "Tempur-Pedic", "Sealy"],
    "AMZN": ["Amazon.com", "AmazonBasics"],
    "TGT": ["Target Corporation"],
    "WMT": ["Walmart", "Wal-Mart"],
    "COST": ["Costco Wholesale", "Kirkland Signature"],
    "HD": ["Home Depot"],
    "LOW": ["Lowe's", "Lowes"],
    "BBY": ["Best Buy"],
    "DE": ["Deere & Company", "John Deere"],
}

_CACHE_TTL_SECONDS = 6 * 3600
_cache: Dict[str, Dict] = {}

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _init_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cpsc_recalls (
            ticker TEXT NOT NULL,
            recall_id TEXT NOT NULL,
            recall_date TEXT,
            payload_json TEXT NOT NULL,
            fetched_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (ticker, recall_id)
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def is_available() -> bool:
    """Always True -- no API key or signup required, same posture as
    openfda_service.py (see that module for the rationale). The current
    live-reliability caveat documented above is an operational issue on
    CPSC's own backend, not a configuration gate on our side."""
    return True


def _persist(ticker: str, items: List[Dict]):
    import json
    if not items:
        return
    try:
        conn = sqlite3.connect(_DB_PATH)
        rows = []
        for r in items:
            recall_id = r.get("RecallID") or r.get("RecallNumber")
            if not recall_id:
                continue
            rows.append((ticker, str(recall_id), r.get("RecallDate"), json.dumps(r)))
        if rows:
            conn.executemany(
                """
                INSERT INTO cpsc_recalls (ticker, recall_id, recall_date, payload_json, fetched_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(ticker, recall_id) DO UPDATE SET
                    recall_date=excluded.recall_date, payload_json=excluded.payload_json, fetched_at=excluded.fetched_at
                """,
                rows,
            )
            conn.commit()
        conn.close()
    except Exception as e:
        logger.info("cpsc_service: failed to persist %s: %s", ticker, e)


def _load_persisted(ticker: str, limit: int = 5) -> List[Dict]:
    import json
    try:
        conn = sqlite3.connect(_DB_PATH)
        rows = conn.execute(
            "SELECT payload_json FROM cpsc_recalls WHERE ticker=? ORDER BY recall_date DESC LIMIT ?",
            (ticker, limit),
        ).fetchall()
        conn.close()
        return [json.loads(r[0]) for r in rows]
    except Exception:
        return []


def _search(keyword: str, limit: int = 5) -> Optional[List[Dict]]:
    """Live query against CPSC's Manufacturer= search, trailing
    _LOOKBACK_DAYS only. Returns a list of raw recall dicts, an empty
    list for a genuine zero-match search, or None on an actual fetch
    failure or a real API-level error response (see module docstring's
    live-reliability note -- CPSC can return HTTP 200 with an error
    payload instead of a proper 5xx, so this checks the payload shape
    too, not just the status code)."""
    since = (datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    until = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    params = {
        "Manufacturer": keyword,
        "RecallDateStart": since,
        "RecallDateEnd": until,
        "format": "json",
    }
    record_run_start(SOURCE_KEY)
    try:
        res = get_with_backoff(CPSC_BASE_URL, params=params, timeout=15)
        if res.status_code != 200:
            logger.info("cpsc_service: %s returned HTTP %s", keyword, res.status_code)
            record_run_error(SOURCE_KEY, f"{keyword}: HTTP {res.status_code}")
            return None
        payload = res.json()
    except Exception as e:
        logger.info("cpsc_service: failed to fetch %s: %s", keyword, e)
        record_run_error(SOURCE_KEY, f"{keyword}: {e}")
        return None

    if not isinstance(payload, list):
        record_run_error(SOURCE_KEY, f"{keyword}: unexpected response shape (not a list)")
        return None

    # CPSC's own quirk (see module docstring): a real fetch/provider
    # failure comes back as HTTP 200 with a single placeholder record
    # whose Title starts with "Error retrieving Recalls:" -- checked
    # explicitly so this is never mistaken for "zero recalls found".
    if len(payload) == 1 and str(payload[0].get("Title") or "").startswith("Error retrieving Recalls"):
        record_run_error(SOURCE_KEY, f"{keyword}: CPSC provider error -- {payload[0].get('Title')}")
        return None

    record_run_success(SOURCE_KEY)
    return payload[:limit]


def _shape_result(r: Dict) -> Dict:
    products = r.get("Products") or [{}]
    manufacturers = r.get("Manufacturers") or [{}]
    hazards = r.get("Hazards") or [{}]
    remedies = r.get("Remedies") or [{}]
    return {
        "recall_id": r.get("RecallID"),
        "recall_number": r.get("RecallNumber"),
        "date": r.get("RecallDate"),
        "title": r.get("Title"),
        "product_name": products[0].get("Name"),
        "manufacturer": manufacturers[0].get("Name"),
        "hazard": hazards[0].get("Name"),
        "remedy": remedies[0].get("Name"),
        "url": r.get("URL"),
    }


def get_recall_context_for_ticker(ticker: str) -> Optional[Dict]:
    """Returns {"matched_ticker", "matched_keywords", "attribution",
    "lookback_days", "count", "recent": [...], "fetch_error"} or None if
    this ticker has no keyword mapping at all."""
    ticker = (ticker or "").upper().strip()
    keywords = _TICKER_TO_KEYWORDS.get(ticker)
    if not keywords:
        return None

    if not is_source_enabled(SOURCE_KEY):
        return {"matched_ticker": ticker, "available": False, "message": "CPSC source暫時停用。"}

    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(ticker)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["result"]

    merged: Dict[str, Dict] = {}
    any_call_failed = False
    for kw in keywords:
        results = _search(kw, limit=5)
        if results is None:
            any_call_failed = True
            continue
        for r in results:
            key = r.get("RecallID") or r.get("RecallNumber")
            if key:
                merged[str(key)] = r

    if merged:
        _persist(ticker, list(merged.values()))
        items = sorted(merged.values(), key=lambda r: r.get("RecallDate") or "", reverse=True)[:5]
        fetch_error = False
    elif any_call_failed:
        items = _load_persisted(ticker, limit=5)
        fetch_error = not items
    else:
        items = []
        fetch_error = False

    result = {
        "matched_ticker": ticker,
        "matched_keywords": keywords,
        "attribution": ATTRIBUTION,
        "lookback_days": _LOOKBACK_DAYS,
        "count": len(items),
        "recent": [_shape_result(r) for r in items],
        "fetch_error": fetch_error,
    }
    _cache[ticker] = {"fetched_at": now, "result": result}
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(get_recall_context_for_ticker("WMT"), indent=2, ensure_ascii=False))
