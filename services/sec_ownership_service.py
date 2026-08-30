"""
SEC EDGAR 13F Institutional Ownership Service -- 2026-08-26, Data
Factory Step 4 (AJ: "混合" FRED + CFTC + SEC EDGAR ownership; addresses
the "Ownership" node type from AJ's pasted Corporate Control Graph
documents).

What this is: institutional investment managers with >$100M AUM must
file Form 13F quarterly, listing every US equity position they hold
(issuer, CUSIP, shares, market value). This is the raw "who owns what"
data the earlier pasted design docs' Control Score concept depends on --
Control Score itself is explicitly OUT of scope for this step (deferred
to a future step once there's enough persisted history to compute
trends from, and once services/asset_master_service.py's CUSIP->ticker
resolution is populated). This step is just: get real 13F holdings into
xfinlab.db, honestly, for a starter set of managers.

Scope decision (why NOT BlackRock/Vanguard/State Street): the largest
index managers file 13F's with tens of thousands of line items each
(BlackRock's is documented at ~50,000 holdings in a single filing) --
parsing/storing that is a different order of engineering problem (needs
streaming XML parsing, heavy storage, and is mostly index-fund noise
that doesn't actually signal a view). This MVP instead tracks
CONCENTRATED stock-picking managers, where a position actually reflects
a considered bet -- the same "smart money" cohort trackers like
WhaleWisdom/Dataroma focus on. Starting list (CIKs confirmed via direct
search against SEC's own filing index, not guessed):
  - Berkshire Hathaway Inc, CIK 1067983
  - Pershing Square Capital Management LP, CIK 1336528
  - Scion Asset Management LLC (Michael Burry), CIK 1649339

Auto-extensible per AJ's ask: the watched-filer list lives in a DB table
(sec_13f_watched_filers), not a hardcoded Python list -- add_watched_
filer() lets an admin (or a future admin.html panel) track a new CIK
without a code change, same self-registration spirit as
data_source_registry.py.

Honesty note on verification: this module's HTTP-fetch and XML-parsing
logic is built strictly from SEC's own published, stable specs (the
EDGAR Form 13F XML Technical Specification's infoTable schema:
nameOfIssuer/cusip/value/shrsOrPrnAmt.sshPrnamt; the standard data.sec.gov
/submissions/CIK##########.json filing-list shape; the standard EDGAR
Archives per-filing index.json). Every one of those shapes was verified
against real SEC documentation/filings before writing this code. What
could NOT be verified from this sandbox is a live end-to-end HTTP round
trip against sec.gov (outbound requests to sec.gov timed out from this
sandboxed dev environment -- likely a bot-defense measure on SEC's side
against non-browser clients, not necessarily present on Railway's
production IPs). The parsing logic itself IS tested here (see the
functional test run before commit) against hand-built fixtures that
match the documented real shapes exactly. First real production run
should be watched via the Data Factory admin panel's error/last_success
fields to confirm the live round trip actually works from Railway.
"""
import logging
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from services.outbound_http import get_with_backoff
from services.data_source_registry import (
    register_source, is_source_enabled, record_run_start,
    record_run_success, record_run_error,
)

logger = logging.getLogger(__name__)

SOURCE_KEY = "sec_13f_ownership"
register_source(SOURCE_KEY, "SEC 13F Institutional Ownership", "ownership")

# Same identifying User-Agent convention as services/fundamentals_service.py
# -- SEC explicitly requires this on every request.
SEC_USER_AGENT = "XFINLABBot/1.0 (+https://www.xfinlab.com; contact: support@xfinlab.com)"

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FILING_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/index.json"
FILING_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{filename}"
ATTRIBUTION = "Data sourced from SEC EDGAR Form 13F filings (sec.gov). Public regulatory filings, not investment advice."

_SEED_FILERS = [
    (1067983, "Berkshire Hathaway Inc"),
    (1336528, "Pershing Square Capital Management LP"),
    (1649339, "Scion Asset Management LLC"),
]

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _get_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_tables():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sec_13f_watched_filers (
            cik INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            added_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sec_13f_holdings (
            filer_cik INTEGER NOT NULL,
            filer_name TEXT,
            period_of_report TEXT NOT NULL,
            issuer_name TEXT,
            cusip TEXT,
            shares INTEGER,
            value_usd INTEGER,
            fetched_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (filer_cik, period_of_report, cusip)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_13f_issuer ON sec_13f_holdings(issuer_name)")
    for cik, name in _SEED_FILERS:
        conn.execute(
            "INSERT INTO sec_13f_watched_filers (cik, name) VALUES (?, ?) ON CONFLICT(cik) DO NOTHING",
            (cik, name),
        )
    conn.commit()
    conn.close()


_init_tables()


def list_watched_filers() -> List[dict]:
    conn = _get_db()
    rows = conn.execute("SELECT * FROM sec_13f_watched_filers ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_watched_filer(cik: int, name: str):
    """Lets an admin track a new institutional manager without touching
    code -- the auto-extensibility AJ asked for, applied to filers
    specifically (data_source_registry.py's self-registration covers
    whole NEW data sources; this covers new entities within this one
    source)."""
    conn = _get_db()
    conn.execute(
        "INSERT INTO sec_13f_watched_filers (cik, name) VALUES (?, ?) ON CONFLICT(cik) DO UPDATE SET name=excluded.name",
        (cik, name),
    )
    conn.commit()
    conn.close()


def _strip_ns(tag: str) -> str:
    """13F info table XML uses a namespaced schema
    (xmlns='http://www.sec.gov/edgar/document/thirteenf/informationtable')
    -- ElementTree keeps the namespace as a '{uri}localname' prefix on
    every tag. Stripping it defensively means this parser doesn't break
    if SEC ever revises the namespace URI/version, since we only ever
    match on local element names."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _fetch_json(url: str):
    res = get_with_backoff(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=20)
    if res.status_code != 200:
        raise RuntimeError(f"HTTP {res.status_code} for {url}")
    return res.json()


def _find_latest_13f_filing(cik: int) -> Optional[dict]:
    """Returns {"accession_nodash": "...", "period_of_report": "YYYY-MM-DD"}
    for the most recent plain 13F-HR (skips 13F-NT notice-only filings
    and 13F-HR/A amendments -- amendments are real but out of scope for
    this MVP's "latest snapshot" use case)."""
    payload = _fetch_json(SUBMISSIONS_URL.format(cik=cik))
    recent = (payload.get("filings") or {}).get("recent") or {}
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    report_dates = recent.get("reportDate", [])
    filing_dates = recent.get("filingDate", [])

    for i, form in enumerate(forms):
        if form == "13F-HR":
            accession_nodash = accessions[i].replace("-", "") if i < len(accessions) else None
            period = report_dates[i] if i < len(report_dates) and report_dates[i] else (
                filing_dates[i] if i < len(filing_dates) else None
            )
            if accession_nodash and period:
                return {"accession_nodash": accession_nodash, "period_of_report": period}
    return None


def _find_infotable_filename(cik: int, accession_nodash: str) -> Optional[str]:
    """The information-table XML's filename varies by filer/filing
    software -- confirmed live against real filings that a plain
    'infotable' substring match alone is NOT reliable (Berkshire
    Hathaway's Q2 2026 13F-HR filing directory has no file with
    'infotable' in its name at all). Tries three strategies in order,
    each more permissive than the last:
      1. Filename contains 'infotable' (the common case -- most filing
         software does use this, e.g. 'form13fInfoTable.xml').
      2. The directory index's own 'type' field says this document IS
         an information table (SEC labels each filed document with a
         type like '13F-HR', 'COVER PAGE', 'INFORMATION TABLE' --
         reading that label instead of guessing from the filename is
         the more robust signal when the filename itself doesn't help).
      3. Last resort: a 13F-HR filing package normally has exactly one
         primary_doc.xml (the cover page) plus exactly one other XML
         file (the information table) -- if that's the shape we see,
         return the non-primary_doc.xml one.
    Returns None only if none of the three strategies finds a candidate."""
    idx = _fetch_json(FILING_INDEX_URL.format(cik=cik, accession_nodash=accession_nodash))
    items = ((idx.get("directory") or {}).get("item")) or []

    for item in items:
        fname = item.get("name", "")
        if "infotable" in fname.lower() and fname.lower().endswith(".xml"):
            return fname

    for item in items:
        fname = item.get("name", "")
        item_type = str(item.get("type", "")).upper()
        if fname.lower().endswith(".xml") and "INFORMATION TABLE" in item_type:
            return fname

    xml_items = [item.get("name", "") for item in items if item.get("name", "").lower().endswith(".xml")]
    non_primary = [f for f in xml_items if f.lower() != "primary_doc.xml"]
    if len(xml_items) == 2 and len(non_primary) == 1:
        return non_primary[0]

    return None


def _parse_infotable_xml(xml_bytes: bytes) -> List[dict]:
    root = ET.fromstring(xml_bytes)
    holdings = []
    for el in root:
        if _strip_ns(el.tag) != "infoTable":
            continue
        row = {"issuer_name": None, "cusip": None, "value_usd": None, "shares": None}
        for child in el:
            local = _strip_ns(child.tag)
            if local == "nameOfIssuer":
                row["issuer_name"] = (child.text or "").strip() or None
            elif local == "cusip":
                row["cusip"] = (child.text or "").strip() or None
            elif local == "value":
                try:
                    # 13F "value" is reported in thousands of USD per SEC's spec
                    row["value_usd"] = int(float((child.text or "0").strip())) * 1000
                except (TypeError, ValueError):
                    row["value_usd"] = None
            elif local == "shrsOrPrnAmt":
                for gc in child:
                    if _strip_ns(gc.tag) == "sshPrnamt":
                        try:
                            row["shares"] = int(float((gc.text or "0").strip()))
                        except (TypeError, ValueError):
                            row["shares"] = None
        if row["cusip"]:  # cusip is this table's join key -- skip anything without one
            holdings.append(row)
    return holdings


def refresh_filer(cik: int, filer_name: str) -> int:
    """Fetches + persists the latest 13F for one filer. Returns the
    number of holdings persisted (0 on any failure -- failure itself is
    recorded via record_run_error, never raised out to the caller so a
    refresh_all() loop over multiple filers can't be aborted by one
    filer's failure)."""
    if not is_source_enabled(SOURCE_KEY):
        return 0
    record_run_start(SOURCE_KEY)
    try:
        filing = _find_latest_13f_filing(cik)
        if not filing:
            record_run_error(SOURCE_KEY, f"CIK {cik} ({filer_name}): no 13F-HR filing found")
            return 0

        filename = _find_infotable_filename(cik, filing["accession_nodash"])
        if not filename:
            record_run_error(SOURCE_KEY, f"CIK {cik} ({filer_name}): info table filename not found in filing index")
            return 0

        doc_url = FILING_DOC_URL.format(cik=cik, accession_nodash=filing["accession_nodash"], filename=filename)
        res = get_with_backoff(doc_url, headers={"User-Agent": SEC_USER_AGENT}, timeout=30)
        if res.status_code != 200:
            record_run_error(SOURCE_KEY, f"CIK {cik} ({filer_name}): HTTP {res.status_code} fetching info table")
            return 0

        holdings = _parse_infotable_xml(res.content)
        if not holdings:
            record_run_error(SOURCE_KEY, f"CIK {cik} ({filer_name}): info table parsed but zero usable rows")
            return 0

        period = filing["period_of_report"]
        conn = _get_db()
        conn.executemany(
            """
            INSERT INTO sec_13f_holdings (filer_cik, filer_name, period_of_report, issuer_name, cusip, shares, value_usd, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(filer_cik, period_of_report, cusip) DO UPDATE SET
                issuer_name=excluded.issuer_name, shares=excluded.shares,
                value_usd=excluded.value_usd, fetched_at=datetime('now')
            """,
            [(cik, filer_name, period, h["issuer_name"], h["cusip"], h["shares"], h["value_usd"]) for h in holdings],
        )
        conn.commit()
        conn.close()
        record_run_success(SOURCE_KEY)
        return len(holdings)
    except Exception as e:
        record_run_error(SOURCE_KEY, f"CIK {cik} ({filer_name}): {e}")
        return 0


def refresh_all() -> Dict[str, int]:
    """Loops every watched filer -- meant to be called from a scheduled
    job (13F filings only change quarterly, so daily/weekly is plenty;
    wiring an actual APScheduler job is a follow-up once this is
    confirmed working live, not part of this foundational step)."""
    results = {}
    for filer in list_watched_filers():
        results[filer["name"]] = refresh_filer(filer["cik"], filer["name"])
    return results


def get_latest_holdings(cik: int, limit: int = 50) -> List[dict]:
    conn = _get_db()
    latest_period = conn.execute(
        "SELECT MAX(period_of_report) AS p FROM sec_13f_holdings WHERE filer_cik=?", (cik,)
    ).fetchone()["p"]
    if not latest_period:
        conn.close()
        return []
    rows = conn.execute(
        "SELECT * FROM sec_13f_holdings WHERE filer_cik=? AND period_of_report=? ORDER BY value_usd DESC LIMIT ?",
        (cik, latest_period, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_holders_of_issuer(issuer_name_substring: str) -> List[dict]:
    """Cross-filer lookup -- 'who among our watched managers holds a
    position matching this name'. Simple substring match on issuer_name
    as filed (not yet resolved through asset_master_service's alias
    table -- CUSIP-based resolution is a follow-up once
    asset_master_service has CUSIPs populated for the tickers this site
    covers)."""
    conn = _get_db()
    rows = conn.execute(
        """
        SELECT * FROM sec_13f_holdings
        WHERE issuer_name LIKE ?
        AND period_of_report = (SELECT MAX(period_of_report) FROM sec_13f_holdings AS h2 WHERE h2.filer_cik = sec_13f_holdings.filer_cik)
        ORDER BY value_usd DESC
        """,
        (f"%{issuer_name_substring}%",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 2026-08-26 (AJ: "畀用戶睇" -- surface this on a per-ticker AI analysis
# page, not just the admin panel): resolves an ordinary stock ticker
# (e.g. "AAPL") to whether any of our watched filers hold it. Own
# lightweight ticker->company-name cache, deliberately NOT sharing
# services/fundamentals_service.py's _load_ticker_cik_map() (same
# company_tickers.json source, same SEC_USER_AGENT convention) because
# that cache only keeps ticker->CIK and discards the "title" field this
# needs for issuer-name matching -- duplicating a small, cheap fetch
# here avoids modifying an already-shipped, already-tested module for
# an unrelated feature.
# ---------------------------------------------------------------------------
TICKER_TITLE_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_TICKER_TITLE_CACHE_TTL_DAYS = 7
_ticker_title_cache = {"data": None, "fetched_at": None}

_NAME_SUFFIXES = re.compile(
    r"\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|LLC|LLP|PLC|L P|LP|THE|CLASS A|CLASS B|CL A|CL B|COM|SA|NV|AG|HOLDINGS?)\b",
    re.IGNORECASE,
)


def _normalize_company_name(name: str) -> str:
    """Loose normalization for matching a 13F-filed issuer name (often
    ALL CAPS, abbreviated, no punctuation -- e.g. 'APPLE INC') against
    SEC's own ticker->title map ('Apple Inc.') -- strips common corporate
    suffixes and punctuation, uppercases, collapses whitespace. Not a
    fuzzy/ML match -- deliberately simple and auditable, matching this
    codebase's honesty-first posture (a wrong match here would falsely
    tell a user an institution holds a stock it doesn't)."""
    if not name:
        return ""
    n = re.sub(r"[^\w\s]", " ", name.upper())
    n = _NAME_SUFFIXES.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()


def _load_ticker_title_map() -> dict:
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
        logger.info("sec_ownership_service: ticker->title map fetch failed: %s", e)
        return cached or {}


def get_ownership_summary(ticker: str) -> Dict:
    """
    Returns:
        {"available": True, "attribution": "...",
         "holders": [{"filer_name": "...", "shares": ..., "value_usd": ...,
                      "period_of_report": "..."}, ...]}
        {"available": False, "message": "..."} if the ticker can't even
        be resolved to a company name (e.g. non-US ticker SEC doesn't
        cover).

    `holders` is an empty list, NOT absence of the "available" key, when
    the ticker resolves fine but none of our watched filers hold it --
    this is the honest reading given we only track 3 concentrated
    managers, not "no institution anywhere owns this stock". Callers
    (the ai-analysis.html UI) should only render a holders section when
    the list is non-empty, to avoid implying a negative signal from a
    simple "we don't track anyone who holds this" result.
    """
    ticker = (ticker or "").upper().strip()
    title_map = _load_ticker_title_map()
    title = title_map.get(ticker)
    if not title:
        return {"available": False, "message": f"{ticker} 唔喺SEC EDGAR嘅美股公司名單入面（可能唔係美股）。"}

    target_norm = _normalize_company_name(title)
    if not target_norm:
        return {"available": False, "message": "無法解析公司名稱。"}

    conn = _get_db()
    rows = conn.execute("""
        SELECT * FROM sec_13f_holdings AS h
        WHERE period_of_report = (
            SELECT MAX(period_of_report) FROM sec_13f_holdings AS h2 WHERE h2.filer_cik = h.filer_cik
        )
    """).fetchall()
    conn.close()

    holders = []
    for r in rows:
        row_norm = _normalize_company_name(r["issuer_name"] or "")
        if row_norm and (row_norm == target_norm or row_norm in target_norm or target_norm in row_norm):
            holders.append({
                "filer_cik": r["filer_cik"],
                "filer_name": r["filer_name"],
                "shares": r["shares"],
                "value_usd": r["value_usd"],
                "period_of_report": r["period_of_report"],
            })

    return {"available": True, "attribution": ATTRIBUTION, "holders": holders}


# ---------------------------------------------------------------------------
# 2026-08-26 (AJ: "起Control Score" -- following up on AJ's original
# pasted "Corporate Control & Capital Intelligence Engine" documents'
# Ownership≠Control concept). Naming/scope decision made here, worth
# stating plainly: this is NOT the "Control Score" those documents
# described. That version needed board seats, voting agreements, proxy
# fights, and 13D/13G activist filings (which signal INTENT to
# influence, unlike 13F's passive quarterly position disclosure) --
# none of which this codebase collects yet. Computing a score called
# "Control" without that data and presenting it to users would be
# exactly the kind of unsupported-precision claim AJ had this same
# session's homepage Win Rate stat removed for ("將個%數字拎走"). So:
# this is honestly named and scoped to what sec_13f_holdings actually
# contains today -- how many of our tracked managers hold a position,
# and how large that position is relative to EACH manager's own total
# reported portfolio (a real, computable proxy for "how much conviction
# does this specific manager have in this specific stock", not a claim
# about influence over the company). A real Control Score is a future
# upgrade once 13D/13G + multi-quarter trend data exists -- tracked as a
# known gap, not silently approximated.
# ---------------------------------------------------------------------------
def _filer_portfolio_total(filer_cik: int, period_of_report: str) -> Optional[int]:
    conn = _get_db()
    row = conn.execute(
        "SELECT SUM(value_usd) AS total FROM sec_13f_holdings WHERE filer_cik=? AND period_of_report=?",
        (filer_cik, period_of_report),
    ).fetchone()
    conn.close()
    total = row["total"] if row else None
    return int(total) if total else None


def get_conviction_score(ticker: str) -> Dict:
    """
    Returns:
        {"available": True, "score": 0-100,
         "breadth": {"holders": 2, "of_tracked": 3},
         "holders_detail": [{"filer_name": "...", "position_pct_of_their_portfolio": 12.4, "value_usd": ...}, ...],
         "methodology": "..."}
        {"available": False, "message": "..."} when the ticker resolves
        but no tracked manager holds it, or can't be resolved at all --
        callers should treat this as "no score to show", never a 0.

    score = 50% breadth (what fraction of our tracked managers hold
    this) + 50% average conviction (each holding manager's position size
    as a % of THEIR OWN total reported 13F portfolio that quarter,
    scaled so a 25%+ portfolio weight maxes out the conviction half --
    concentrated managers rarely go much higher than that in one name,
    so this avoids a single mega-bet swamping the scale). Both halves
    are simple, auditable, and traceable back to real persisted numbers
    -- no hidden weighting, no external benchmark.
    """
    summary = get_ownership_summary(ticker)
    if not summary.get("available") or not summary.get("holders"):
        return {"available": False, "message": "冇追蹤緊嘅機構持有呢隻股票，未能計算Conviction Score。"}

    holders = summary["holders"]
    total_tracked = len(list_watched_filers())
    breadth_score = (len(holders) / total_tracked * 100) if total_tracked else 0

    holders_detail = []
    conviction_values = []
    for h in holders:
        portfolio_total = _filer_portfolio_total(h["filer_cik"], h["period_of_report"])
        pct = None
        if portfolio_total and h["value_usd"]:
            pct = round(h["value_usd"] / portfolio_total * 100, 2)
            conviction_values.append(min(pct / 25 * 100, 100))
        holders_detail.append({
            "filer_name": h["filer_name"],
            "value_usd": h["value_usd"],
            "position_pct_of_their_portfolio": pct,
        })

    avg_conviction = (sum(conviction_values) / len(conviction_values)) if conviction_values else 0
    score = round(0.5 * breadth_score + 0.5 * avg_conviction, 1)

    # 2026-08-26 ("做下一步" after the 13D/13G collector shipped): this is
    # the real "intent to influence" ingredient the module docstring
    # said the score was missing. Deliberately kept as its OWN clearly
    # labeled field, NOT blended into the numeric score above -- folding
    # a boolean "someone filed an activist 13D" into a continuous 0-100
    # number would hide the real reason behind a score jump and imply a
    # false precision (e.g. "conviction went from 60 to 85" tells a user
    # nothing when the actual story is "an activist showed up"). Keeping
    # them visually/structurally separate lets the UI say the honest
    # thing directly: "3 managers hold this AND an activist just filed a
    # 13D" is a very different, much more specific claim than a single
    # blended number.
    activist_signal = {"has_recent_13d": False, "filers": []}
    try:
        from services.sec_13d_13g_service import search_recent_filings as _search_13d13g
        activity = _search_13d13g(ticker)
        if activity.get("available"):
            thirteen_ds = [f for f in activity.get("filings", []) if "13D" in (f.get("form_type") or "").upper()]
            if thirteen_ds:
                activist_signal = {
                    "has_recent_13d": True,
                    "filers": [{"filer_display_name": f["filer_display_name"], "file_date": f["file_date"]} for f in thirteen_ds],
                }
    except Exception:
        pass  # best-effort -- a 13D/13G lookup failure must never break the conviction score itself

    return {
        "available": True,
        "score": score,
        "breadth": {"holders": len(holders), "of_tracked": total_tracked},
        "holders_detail": holders_detail,
        "activist_signal": activist_signal,
        "methodology": "50% breadth (share of tracked managers holding this) + 50% average conviction (each holder's position as a % of their own total 13F portfolio, capped at 25%+ = max). activist_signal is separate and NOT part of the 0-100 score -- see module docstring on why. Not a measure of corporate control or influence.",
    }


# ---------------------------------------------------------------------------
# 2026-08-30 (Company Network Phase 4, AJ: "2 3 做啦" picking option 2 of a
# 3-option next-feature menu -- "cross-ticker fund overlap, zero new data
# source, pure re-package of already-collected 13F data"). What this adds
# that get_ownership_summary()/get_conviction_score() don't: those two
# only ever look at ONE ticker's slice of sec_13f_holdings. But every
# 13F filing already persisted in that table has EVERY position the
# filer reported that quarter, not just the one the caller asked about
# -- so for a tracked manager that holds this ticker, we already have
# their full other holdings sitting in the same table, unused until now.
#
# Deliberately not a "smart money score" or ranking -- just literal rows
# from real filings: which of our tracked concentrated managers hold
# this ticker, and what else (by real reported value) that SAME manager
# holds. No CUSIP->ticker resolution exists yet (see module docstring),
# so "other holdings" are shown by their real SEC-reported issuer name,
# never guessed at a ticker symbol.
def get_smart_money_crossholdings(ticker: str, other_limit: int = 5) -> Dict:
    """
    Returns:
        {"available": True, "attribution": "...",
         "watched_filers_note": "...",
         "crossholdings": [
             {"filer_name": "...", "filer_cik": ..., "period_of_report": "...",
              "position_in_ticker": {"shares": ..., "value_usd": ...},
              "other_top_holdings": [{"issuer_name": "...", "value_usd": ..., "shares": ...}, ...]},
             ...
         ]}
        {"available": False, "message": "..."} when the ticker resolves
        but none of our tracked managers hold it, or can't be resolved.

    `other_top_holdings` is capped at `other_limit` (default 5), sorted
    by real reported value_usd descending, and always excludes the
    queried ticker's own issuer row (that's already in position_in_ticker).
    """
    summary = get_ownership_summary(ticker)
    if not summary.get("available") or not summary.get("holders"):
        return {"available": False, "message": "冇追蹤緊嘅機構持有呢隻股票，未能睇到相關持倉。"}

    title_map = _load_ticker_title_map()
    target_title = title_map.get((ticker or "").upper().strip()) or ""
    target_norm = _normalize_company_name(target_title)

    conn = _get_db()
    crossholdings = []
    for h in summary["holders"]:
        rows = conn.execute(
            "SELECT issuer_name, shares, value_usd FROM sec_13f_holdings "
            "WHERE filer_cik=? AND period_of_report=? ORDER BY value_usd DESC",
            (h["filer_cik"], h["period_of_report"]),
        ).fetchall()
        other = []
        for r in rows:
            row_norm = _normalize_company_name(r["issuer_name"] or "")
            if target_norm and row_norm and (row_norm == target_norm or row_norm in target_norm or target_norm in row_norm):
                continue  # this is the queried ticker itself -- already in position_in_ticker
            other.append({"issuer_name": r["issuer_name"], "value_usd": r["value_usd"], "shares": r["shares"]})
            if len(other) >= other_limit:
                break
        crossholdings.append({
            "filer_name": h["filer_name"],
            "filer_cik": h["filer_cik"],
            "period_of_report": h["period_of_report"],
            "position_in_ticker": {"shares": h["shares"], "value_usd": h["value_usd"]},
            "other_top_holdings": other,
        })
    conn.close()

    watched = list_watched_filers()
    return {
        "available": True,
        "attribution": ATTRIBUTION,
        "watched_filers_note": (
            f"Tracks {len(watched)} concentrated, stock-picking managers ({', '.join(w['name'] for w in watched)}) "
            "-- not a comprehensive institutional universe. See sec_ownership_service.py's module docstring for why "
            "large index managers (BlackRock/Vanguard/State Street) aren't tracked here."
        ),
        "crossholdings": crossholdings,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(refresh_all(), indent=2))
