"""
openFDA Consumer Safety Signals -- 2026-08-31 (AJ: "感官與消費者科學"
follow-up -> researched 3 candidate consumer-science data sources,
AJ picked openFDA (recalls) + openFDA Food Adverse Events over a
standalone USDA ERS "Food Dollar" integration, which was rejected after
verification: its dataset hasn't been updated since March 2020 and its
own "Food Dollar API" resource link on catalog.data.gov 404s -- an
honestly-scoped rejection, not a guess (see chat for the verification).

What this is: FDA-regulated product RECALLS (food/drug/device
enforcement actions) and food-specific consumer ADVERSE EVENT reports
(CAERS -- Consumer Adverse Event Reporting System), per-ticker via an
explicit keyword map, same "no fabricated match for an unmapped ticker"
convention as every other Data Factory collector. Event-driven, same
shape family as services/sec_13d_13g_service.py's search_recent_
filings() (a live per-request EDGAR full-text search) rather than the
FRED-style cached time-series modules -- there is no single "current
value" for a recall/adverse-event stream, only a recent window.

Source verified live, 2026-08-31, by directly querying each endpoint
(not assumed from documentation alone):
  - https://api.fda.gov/food/enforcement.json
  - https://api.fda.gov/drug/enforcement.json
  - https://api.fda.gov/device/enforcement.json
  - https://api.fda.gov/food/event.json (CAERS)
All 4 share consistent openFDA conventions: `search=field:"term"` query
syntax, `limit=` (max 1000/call), and -- a real, documented quirk worth
noting explicitly -- a zero-match search returns HTTP 404 with
`{"error":{"code":"NOT_FOUND",...}}`, NOT HTTP 200 with an empty
`results` array. This module treats that 404 as "zero results, not an
error" (see _search_dataset below) -- getting this wrong would either
mask real fetch failures as "no recalls" or flag every unmapped/quiet
ticker as a fetch error, both dishonest.

Genuinely unlike every other Data Factory collector: no signup, no API
key required at all for this call volume (an optional key only raises
the rate limit -- see OPENFDA_API_KEY_ENV below). is_available() is
hardcoded True; is_source_enabled() (the admin on/off toggle every
collector already respects) is still honored.

The 3 enforcement datasets search on `recalling_firm` (the parent legal
entity), while food_adverse_events searches on `products.name_brand`
(the consumer-facing brand) -- these differ a lot for one public
company (e.g. KHC's legal recalling_firm is "Kraft Heinz Foods", but
its adverse-event reports show up under "Kraft", "Oscar Mayer",
"Jell-O", etc. as the product brand). _TICKER_TO_KEYWORDS below lists
every keyword tried against BOTH field types per ticker -- broader
recall, same "explicit mapping, no guessing" discipline as every other
_TICKER_TO_* table in this codebase.

CAERS honesty note, direct from openFDA's own API disclaimer (also
surfaced verbatim in ATTRIBUTION below): "Submission of an adverse
event report does not constitute an admission that a product caused or
contributed to an event... cannot be used to estimate incidence or
risk." A report existing is not proof of causation -- this module
never editorializes past what the raw report says.
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

OPENFDA_BASE_URL = "https://api.fda.gov"
OPENFDA_API_KEY_ENV = "OPENFDA_API_KEY"  # optional -- raises the rate limit only, never gates availability
ATTRIBUTION = (
    "Data sourced from the U.S. Food & Drug Administration's openFDA API (api.fda.gov). "
    "Not an endorsement or official FDA communication. Per openFDA's own terms: submission of an "
    "adverse event report does not constitute an admission that a product caused or contributed to "
    "an event, and this data should not be used to estimate incidence or risk."
)

SOURCE_KEY = "openfda_consumer_safety"
register_source(SOURCE_KEY, "openFDA Recalls & Adverse Events", "consumer_safety")

# Trailing window searched per call -- recalls/adverse events are
# event-driven with no natural "current value"; a 12-month window is
# recent enough to be relevant to today's business while wide enough
# that a real but infrequent event isn't missed on most calls.
_LOOKBACK_DAYS = 365

_DATASETS = {
    "food_recalls": {"endpoint": "food/enforcement", "search_field": "recalling_firm", "date_field": "report_date"},
    "drug_recalls": {"endpoint": "drug/enforcement", "search_field": "recalling_firm", "date_field": "report_date"},
    "device_recalls": {"endpoint": "device/enforcement", "search_field": "recalling_firm", "date_field": "report_date"},
    "food_adverse_events": {"endpoint": "food/event", "search_field": "products.name_brand", "date_field": "date_created"},
}

# ticker -> keywords tried against every dataset above (recalling_firm
# for the 3 enforcement datasets, products.name_brand for adverse
# events). Deliberately explicit and small -- large public food/CPG/
# pharma/device companies with real, well-known brand names, not a
# guessed or auto-derived list. A ticker not listed here gets None from
# get_consumer_safety_context_for_ticker(), never a fabricated "no
# recalls" reading for a company this module never actually checked.
_TICKER_TO_KEYWORDS = {
    "KHC": ["Kraft Heinz", "Kraft", "Heinz", "Oscar Mayer", "Jell-O", "Philadelphia", "Velveeta"],
    "GIS": ["General Mills", "Cheerios", "Betty Crocker", "Pillsbury", "Yoplait"],
    "K": ["Kellanova", "Kellogg", "Pringles", "Pop-Tarts", "Cheez-It"],
    "CPB": ["Campbell", "Pepperidge Farm", "Prego"],
    "CAG": ["Conagra", "Marie Callender", "Slim Jim", "Healthy Choice"],
    "MDLZ": ["Mondelez", "Oreo", "Ritz", "Nabisco"],
    "HSY": ["Hershey"],
    "TSN": ["Tyson Foods", "Tyson", "Jimmy Dean", "Hillshire"],
    "SJM": ["J.M. Smucker", "Smucker", "Jif", "Folgers"],
    "PEP": ["PepsiCo", "Frito-Lay", "Quaker", "Gatorade"],
    "KO": ["Coca-Cola"],
    "PG": ["Procter & Gamble", "Procter and Gamble"],
    "CL": ["Colgate-Palmolive", "Colgate"],
    "CHD": ["Church & Dwight", "Arm & Hammer"],
    "CLX": ["Clorox"],
    "KMB": ["Kimberly-Clark", "Kimberly Clark", "Huggies", "Kleenex"],
    "JNJ": ["Johnson & Johnson", "Johnson and Johnson"],
    "PFE": ["Pfizer"],
    "MRK": ["Merck"],
    "ABBV": ["AbbVie"],
    "BMY": ["Bristol-Myers Squibb", "Bristol Myers"],
    "LLY": ["Eli Lilly", "Lilly"],
    "MDT": ["Medtronic"],
    "ABT": ["Abbott Laboratories", "Abbott"],
    "SYK": ["Stryker"],
    "BSX": ["Boston Scientific"],
    "ZBH": ["Zimmer Biomet"],
    "BAX": ["Baxter International", "Baxter"],
}

_CACHE_TTL_SECONDS = 6 * 3600
_cache: Dict[str, Dict] = {}  # ticker -> {"fetched_at": epoch, "result": {...}}

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _init_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS openfda_events (
            ticker TEXT NOT NULL,
            dataset TEXT NOT NULL,
            event_key TEXT NOT NULL,
            event_date TEXT,
            payload_json TEXT NOT NULL,
            fetched_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (ticker, dataset, event_key)
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def is_available() -> bool:
    """Always True -- see module docstring: openFDA needs no signup or
    key for this call volume. Kept as a function (not a bare constant)
    so every call site that checks `<module>.is_available()` before
    surfacing a section works identically to every other Data Factory
    module, with no special-casing needed at the call site."""
    return True


def _persist(ticker: str, dataset_key: str, items: List[Dict], date_field: str, key_field_candidates: List[str]):
    import json
    if not items:
        return
    try:
        conn = sqlite3.connect(_DB_PATH)
        rows = []
        for r in items:
            event_key = next((r.get(k) for k in key_field_candidates if r.get(k)), None)
            if not event_key:
                continue
            rows.append((ticker, dataset_key, str(event_key), r.get(date_field), json.dumps(r)))
        if rows:
            conn.executemany(
                """
                INSERT INTO openfda_events (ticker, dataset, event_key, event_date, payload_json, fetched_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(ticker, dataset, event_key) DO UPDATE SET
                    event_date=excluded.event_date, payload_json=excluded.payload_json, fetched_at=excluded.fetched_at
                """,
                rows,
            )
            conn.commit()
        conn.close()
    except Exception as e:
        logger.info("openfda_service: failed to persist %s/%s: %s", ticker, dataset_key, e)


def _load_persisted(ticker: str, dataset_key: str, limit: int = 5) -> List[Dict]:
    import json
    try:
        conn = sqlite3.connect(_DB_PATH)
        rows = conn.execute(
            "SELECT payload_json FROM openfda_events WHERE ticker=? AND dataset=? ORDER BY event_date DESC LIMIT ?",
            (ticker, dataset_key, limit),
        ).fetchall()
        conn.close()
        return [json.loads(r[0]) for r in rows]
    except Exception:
        return []


def _search_dataset(dataset_key: str, keyword: str, limit: int = 5) -> Optional[List[Dict]]:
    """Live query against one openFDA dataset for a single keyword,
    trailing _LOOKBACK_DAYS only. Returns a list of raw result dicts
    (newest first), an empty list for a genuine zero-match search (see
    module docstring on openFDA's 404-means-empty quirk), or None only
    on an actual fetch failure (recorded via record_run_error, never
    silently treated as "no results")."""
    meta = _DATASETS[dataset_key]
    since = (datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y%m%d")
    until = datetime.now(timezone.utc).strftime("%Y%m%d")
    search = f'{meta["search_field"]}:"{keyword}" AND {meta["date_field"]}:[{since} TO {until}]'
    params = {"search": search, "limit": limit, "sort": f'{meta["date_field"]}:desc'}
    if os.getenv(OPENFDA_API_KEY_ENV):
        params["api_key"] = os.getenv(OPENFDA_API_KEY_ENV)

    record_run_start(SOURCE_KEY)
    try:
        res = get_with_backoff(f"{OPENFDA_BASE_URL}/{meta['endpoint']}.json", params=params, timeout=15)
        if res.status_code == 404:
            # openFDA's own documented behavior: zero matches -> HTTP 404
            # with an {"error": {"code": "NOT_FOUND", ...}} body, not a
            # 200 with an empty array. A real, verified quirk (see module
            # docstring) -- this is "no recalls found", not a failure.
            record_run_success(SOURCE_KEY)
            return []
        if res.status_code != 200:
            logger.info("openfda_service: %s/%s returned HTTP %s", dataset_key, keyword, res.status_code)
            record_run_error(SOURCE_KEY, f"{dataset_key}/{keyword}: HTTP {res.status_code}")
            return None
        payload = res.json()
    except Exception as e:
        logger.info("openfda_service: failed to fetch %s/%s: %s", dataset_key, keyword, e)
        record_run_error(SOURCE_KEY, f"{dataset_key}/{keyword}: {e}")
        return None

    record_run_success(SOURCE_KEY)
    return payload.get("results") or []


def _shape_result(dataset_key: str, r: Dict) -> Dict:
    """Trims a raw openFDA result to the fields worth showing a reader --
    same 'no raw feed dump' posture as every other Data Factory field."""
    if dataset_key == "food_adverse_events":
        products = r.get("products") or [{}]
        return {
            "report_number": r.get("report_number"),
            "date": r.get("date_created"),
            "product_brand": products[0].get("name_brand"),
            "reactions": r.get("reactions") or [],
            "outcomes": r.get("outcomes") or [],
        }
    return {
        "recall_number": r.get("recall_number"),
        "date": r.get("report_date"),
        "status": r.get("status"),
        "classification": r.get("classification"),
        "recalling_firm": r.get("recalling_firm"),
        "product_description": r.get("product_description"),
        "reason_for_recall": r.get("reason_for_recall"),
        "voluntary_mandated": r.get("voluntary_mandated"),
    }


_KEY_FIELD_CANDIDATES = ["recall_number", "report_number", "event_id"]


def get_consumer_safety_context_for_ticker(ticker: str) -> Optional[Dict]:
    """Returns {"matched_ticker", "matched_keywords", "attribution",
    "lookback_days", "datasets": {dataset_key: {"count", "recent": [...],
    "fetch_error": bool}}} or None if this ticker has no keyword mapping
    at all (never a fabricated reading for an unmapped company).

    `fetch_error` on a sub-dataset is True only when every live call for
    that dataset failed AND no persisted fallback rows existed either --
    a genuine zero-recall result (openFDA's 404-means-empty, see above)
    is never reported as an error."""
    ticker = (ticker or "").upper().strip()
    keywords = _TICKER_TO_KEYWORDS.get(ticker)
    if not keywords:
        return None

    if not is_source_enabled(SOURCE_KEY):
        return {"matched_ticker": ticker, "available": False, "message": "openFDA source暫時停用。"}

    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(ticker)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["result"]

    datasets_out: Dict[str, Dict] = {}
    for dataset_key, meta in _DATASETS.items():
        merged: Dict[str, Dict] = {}
        any_call_failed = False
        for kw in keywords:
            results = _search_dataset(dataset_key, kw, limit=5)
            if results is None:
                any_call_failed = True
                continue
            for r in results:
                key = next((r.get(k) for k in _KEY_FIELD_CANDIDATES if r.get(k)), None)
                if key:
                    merged[str(key)] = r

        if merged:
            _persist(ticker, dataset_key, list(merged.values()), meta["date_field"], _KEY_FIELD_CANDIDATES)
            items = sorted(merged.values(), key=lambda r: r.get(meta["date_field"]) or "", reverse=True)[:5]
            fetch_error = False
        elif any_call_failed:
            # every live call for this dataset failed -- fall back to
            # whatever was last persisted rather than claiming "zero
            # recalls" when we genuinely don't know.
            persisted = _load_persisted(ticker, dataset_key, limit=5)
            items = persisted
            fetch_error = not persisted
        else:
            items = []
            fetch_error = False

        datasets_out[dataset_key] = {
            "count": len(items),
            "recent": [_shape_result(dataset_key, r) for r in items],
            "fetch_error": fetch_error,
        }

    result = {
        "matched_ticker": ticker,
        "matched_keywords": keywords,
        "attribution": ATTRIBUTION,
        "lookback_days": _LOOKBACK_DAYS,
        "datasets": datasets_out,
    }
    _cache[ticker] = {"fetched_at": now, "result": result}
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(get_consumer_safety_context_for_ticker("KHC"), indent=2, ensure_ascii=False))
