"""
SEC EDGAR Schedule 13D / 13G Beneficial Ownership Service -- 2026-08-26,
Data Factory Step 6 (AJ: "起13D/13G維權申報collector", the piece the
"起Control Score" conversation flagged as missing -- see
sec_ownership_service.get_conviction_score's docstring for the earlier
scoping decision that deliberately deferred "Control" claims until this
existed).

What this is, and why it's different from the 13F collector: Schedule
13D and 13G are filed by an acquirer the moment they cross 5%
beneficial ownership of a public company's stock -- unlike 13F (a
manager's routine quarterly inventory of ALL their positions), a 13D/
13G is filed PER STAKE, triggered by an event. Critically: 13D signals
INTENT to influence or control the company (activist investors,
proxy fights, board seats) while 13G signals a PASSIVE stake (no intent
to influence -- typically index funds/passive managers who happen to
cross 5% just by tracking an index). That intent distinction is exactly
what 13F alone can never tell you, and is the real missing ingredient
for anything that wants to talk about "control" rather than just
"ownership".

Data source: SEC's EDGAR full-text search API (efts.sec.gov/LATEST/
search-index) -- a different SEC system from data.sec.gov/sec.gov/
Archives used by fundamentals_service.py and sec_ownership_service.py,
but same no-key-required, same User-Agent requirement, same 10 req/sec
shared EDGAR rate limit. Chosen over trying to filter data.sec.gov's
per-company submissions.json because 13D/13G filings are indexed under
the ACQUIRER's own CIK, not the subject company's -- there is no
"list every 13D/13G filed about ticker X" endpoint in the structured
API; full-text search (searching for the subject company's name within
SC 13D/SC 13G filings) is the standard, documented way every third-party
EDGAR tool does this lookup.

Shape difference from every other collector in this codebase: this is
an ON-DEMAND per-ticker lookup (triggered when a user views that
ticker's AI analysis), not a scheduled batch job over a fixed watchlist
like FRED/CFTC/13F. It still self-registers with data_source_registry.py
(so run/error/enable-disable show up in the same Data Factory admin
panel) and still persists every real hit it finds into xfinlab.db, so a
history builds up over time from real usage even without a dedicated
cron.

Honesty note on verification (same posture as sec_ownership_service.py's
13F work): the request/response shapes here are built from SEC's own
documented EFTS API behavior, cross-checked against multiple independent
technical write-ups, not guessed. But the exact field names in `_source`
(entity_name vs display_names, form vs form_type) have some documented
inconsistency across sources/API versions -- this module defensively
tries multiple known field names for each value rather than assuming
one, and /admin/sec-13d13g-debug (added alongside this) surfaces the
RAW hit object so a live mismatch can be diagnosed in one round-trip
instead of several, unlike the 13F info-table filename bug which took
multiple back-and-forth debugging rounds with AJ to pin down.
"""
import logging
import os
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from services.outbound_http import get_with_backoff
from services.data_source_registry import (
    register_source, is_source_enabled, record_run_start,
    record_run_success, record_run_error,
)

logger = logging.getLogger(__name__)

SOURCE_KEY = "sec_13d_13g_activism"
register_source(SOURCE_KEY, "SEC 13D/13G Activist & Passive Ownership Filings", "ownership")

SEC_USER_AGENT = "XFINLABBot/1.0 (+https://www.xfinlab.com; contact: support@xfinlab.com)"
EFTS_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
ATTRIBUTION = "Data sourced from SEC EDGAR full-text search (efts.sec.gov). Public regulatory filings, not investment advice."

_LOOKUP_CACHE_TTL_HOURS = 24  # 13D/13G filings are infrequent/event-driven -- no need to re-search more than daily per ticker
_LOOKBACK_DAYS = 180  # only surface reasonably recent activity, not a company's entire multi-year 13D/13G history
_lookup_cache: Dict[str, Dict] = {}  # ticker -> {"fetched_at": epoch, "result": {...}}

_TICKER_TITLE_CACHE_TTL_DAYS = 7
_ticker_title_cache = {"data": None, "fetched_at": None}
TICKER_TITLE_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _get_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sec_13d_13g_filings (
            accession TEXT NOT NULL,
            filename TEXT NOT NULL,
            ticker TEXT NOT NULL,
            subject_company_name TEXT,
            form_type TEXT,
            filer_display_name TEXT,
            file_date TEXT,
            doc_url TEXT,
            fetched_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (accession, filename)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_13d13g_ticker ON sec_13d_13g_filings(ticker)")
    conn.commit()
    conn.close()


_init_table()


def _load_ticker_title_map() -> dict:
    """Same lightweight ticker->company-title cache pattern as
    sec_ownership_service.py -- deliberately duplicated (see that
    module's own docstring on why: avoids coupling to a module whose
    cache is scoped for a different purpose)."""
    today = date.today()
    cached = _ticker_title_cache["data"]
    fetched_at = _ticker_title_cache["fetched_at"]
    if cached and fetched_at and (today - fetched_at).days < _TICKER_TITLE_CACHE_TTL_DAYS:
        return cached
    try:
        res = get_with_backoff(TICKER_TITLE_MAP_URL, headers={"User-Agent": SEC_USER_AGENT}, timeout=20)
        if res.status_code != 200:
            return cached or {}
        payload = res.json()
        mapping = {str(e["ticker"]).upper(): e.get("title", "") for e in payload.values()}
        _ticker_title_cache["data"] = mapping
        _ticker_title_cache["fetched_at"] = today
        return mapping
    except Exception as e:
        logger.info("sec_13d_13g_service: ticker->title map fetch failed: %s", e)
        return cached or {}


def _extract_hit_fields(hit: dict) -> dict:
    """Defensive field extraction -- see module docstring on why: EFTS
    `_source` field names have documented inconsistency (entity_name vs
    display_names, form vs form_type) across different API
    versions/write-ups. Tries each known alias in order, never raises on
    a missing field."""
    source = hit.get("_source", {}) or {}
    form_type = source.get("form") or source.get("form_type") or source.get("root_form") or ""
    file_date = source.get("file_date") or ""

    filer_name = None
    display_names = source.get("display_names")
    if isinstance(display_names, list) and display_names:
        filer_name = display_names[0]
    elif source.get("entity_name"):
        filer_name = source.get("entity_name")

    hit_id = hit.get("_id", "")
    accession, _, filename = hit_id.partition(":")
    return {
        "accession": accession,
        "filename": filename,
        "form_type": form_type.strip(),
        "filer_display_name": filer_name,
        "file_date": file_date,
    }


def _doc_url(accession: str, filename: str) -> Optional[str]:
    if not accession or not filename:
        return None
    accession_nodash = accession.replace("-", "")
    # CIK isn't known from the search hit alone -- SEC's Archives path
    # needs a CIK segment, but accepts the FILER's CIK, which full-text
    # search doesn't return directly per-hit either. Using the
    # accession-only EDGAR viewer URL instead, which SEC supports and
    # resolves without needing the CIK segment.
    return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum=&accession_number={accession}"


def search_recent_filings(ticker: str, force_refresh: bool = False) -> Dict:
    """
    Returns:
        {"available": True, "attribution": "...", "subject_company": "...",
         "filings": [{"form_type": "SC 13D", "filer_display_name": "...",
                      "file_date": "...", "doc_url": "..."}, ...]}
        {"available": False, "message": "..."} if the ticker can't be
        resolved to a company name at all.

    `filings` is an empty list, not absence of "available", when the
    company resolves but no 13D/13G activity is found in the lookback
    window -- honest reading, matches sec_ownership_service.py's
    get_ownership_summary() convention exactly.
    """
    ticker = (ticker or "").upper().strip()
    now = datetime.now(timezone.utc).timestamp()
    cached = _lookup_cache.get(ticker)
    if not force_refresh and cached and (now - cached["fetched_at"]) < _LOOKUP_CACHE_TTL_HOURS * 3600:
        return cached["result"]

    title_map = _load_ticker_title_map()
    title = title_map.get(ticker)
    if not title:
        return {"available": False, "message": f"{ticker} 唔喺SEC EDGAR嘅美股公司名單入面（可能唔係美股）。"}

    if not is_source_enabled(SOURCE_KEY):
        # Serve cache if we have anything at all, even if stale -- never
        # a live fetch while admin has this source paused.
        return (cached["result"] if cached else {"available": False, "message": "Source disabled by admin."})

    record_run_start(SOURCE_KEY)
    end_dt = date.today()
    start_dt = end_dt - timedelta(days=_LOOKBACK_DAYS)
    params = {
        "q": f'"{title}"',
        "forms": "SC 13D,SC 13G",
        "dateRange": "custom",
        "startdt": start_dt.isoformat(),
        "enddt": end_dt.isoformat(),
        "size": 20,
    }
    try:
        res = get_with_backoff(EFTS_SEARCH_URL, params=params, headers={"User-Agent": SEC_USER_AGENT}, timeout=20)
        if res.status_code != 200:
            record_run_error(SOURCE_KEY, f"{ticker}: HTTP {res.status_code}")
            result = {"available": False, "message": "SEC EDGAR搜尋暫時未能回應。"}
            _lookup_cache[ticker] = {"fetched_at": now, "result": result}
            return result
        payload = res.json()
    except Exception as e:
        record_run_error(SOURCE_KEY, f"{ticker}: {e}")
        result = {"available": False, "message": "SEC EDGAR搜尋暫時未能回應。"}
        _lookup_cache[ticker] = {"fetched_at": now, "result": result}
        return result

    hits = ((payload.get("hits") or {}).get("hits")) or []
    filings = []
    for hit in hits:
        f = _extract_hit_fields(hit)
        if not f["form_type"].upper().replace("/A", "").strip().startswith("SC 13"):
            continue  # defensive -- only keep genuine 13D/13G family forms even if the search matched something else
        f["doc_url"] = _doc_url(f["accession"], f["filename"])
        filings.append(f)

    _persist_filings(ticker, title, filings)
    record_run_success(SOURCE_KEY)

    result = {"available": True, "attribution": ATTRIBUTION, "subject_company": title, "filings": filings}
    _lookup_cache[ticker] = {"fetched_at": now, "result": result}
    return result


def _persist_filings(ticker: str, subject_company_name: str, filings: List[dict]):
    if not filings:
        return
    try:
        conn = _get_db()
        conn.executemany(
            """
            INSERT INTO sec_13d_13g_filings
                (accession, filename, ticker, subject_company_name, form_type, filer_display_name, file_date, doc_url, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(accession, filename) DO UPDATE SET fetched_at=datetime('now')
            """,
            [
                (f["accession"], f["filename"], ticker, subject_company_name, f["form_type"],
                 f["filer_display_name"], f["file_date"], f["doc_url"])
                for f in filings if f["accession"] and f["filename"]
            ],
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("sec_13d_13g_service: failed to persist filings for %s: %s", ticker, e)


def get_persisted_filings(ticker: str, limit: int = 20) -> List[dict]:
    """Read-only, no live fetch -- for the admin panel's history view."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM sec_13d_13g_filings WHERE ticker=? ORDER BY file_date DESC LIMIT ?",
        (ticker.upper().strip(), limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    import json
    print(json.dumps(search_recent_filings("AAPL"), indent=2, ensure_ascii=False))
