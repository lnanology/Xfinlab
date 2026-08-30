"""
SEC 10-K Business/Risk-Factor Relationship Mentions -- 2026-08-30
(Company Network Phase 2, per AJ's "起 Phase 2 3 一次過").

What this is: every other SEC-backed Data Factory module (13F, 13D/13G,
Form 4, XBRL facts) only ever touches SEC's structured JSON APIs -- none
of them fetch the actual PROSE TEXT of a filing. This module is the
first one that does: it fetches the issuer's own most recent 10-K
document (the real HTML filing, not a numeric API), and extracts
sentences from the "Item 1. Business" / "Item 1A. Risk Factors" sections
that name another company alongside a competitor/supplier/customer
relationship word.

Honesty posture -- READ BEFORE CHANGING THE EXTRACTION LOGIC:
This is deliberately NOT a company-name classifier or true named-entity
recognition (no NLP model is used or bundled). It is a keyword +
corporate-suffix regex match. That means it WILL occasionally miss a
real relationship (understated) and can occasionally match a phrase
that happens to look like a company name but isn't (a residual false-
positive rate). To keep this honest and useful despite that:
  1. Every result carries the literal sentence it was pulled from --
     never a cleaned/inferred "Company X is a competitor" claim. The
     user (or Phase 3) always has the real quote to judge for themselves.
  2. Every result carries `source_filing.url` pointing at the real,
     public 10-K document on sec.gov -- independently verifiable.
  3. `method_note` in every response explains this is pattern matching,
     not NER, in plain language.
This mirrors the same "no fabricated numbers" contract the rest of the
Intelligence API is built on -- here extended to "no fabricated
relationships", not just no fabricated numbers.

Ticker->CIK resolution is this module's own independent copy (same
deliberate non-shared-lookup convention as every other SEC collector in
this codebase -- see sec_form4_service.py's module docstring).

Network round trips could not be verified from this sandbox (outbound
sec.gov calls are blocked here, same known limitation as every other SEC
collector built during this project -- see sec_ownership_service.py's
module docstring). Parsing logic below is written strictly from SEC's
documented submissions.json shape and standard 10-K structure, and
should be watched via the Data Factory admin panel's error/last_success
fields on first real production run.
"""
import logging
import os
import re
import sqlite3
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from services.outbound_http import get_with_backoff
from services.data_source_registry import (
    register_source, is_source_enabled, record_run_start,
    record_run_success, record_run_error,
)

logger = logging.getLogger(__name__)

SEC_USER_AGENT = "XFINLABBot/1.0 (+https://www.xfinlab.com; contact: support@xfinlab.com)"
ATTRIBUTION = (
    "Sentences pattern-matched from the issuer's own most recent 10-K "
    "(SEC EDGAR, sec.gov) Item 1/1A text. Not endorsed or certified by "
    "the SEC. Not a verified relationship database -- for research "
    "reference only, not investment advice."
)

TICKER_CIK_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_TICKER_CIK_CACHE_TTL_DAYS = 7
_ticker_cik_cache = {"data": None, "fetched_at": None}

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
FILING_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{filename}"

SOURCE_KEY = "sec_business_text"
register_source(SOURCE_KEY, "SEC 10-K Business/Risk-Factor Mentions", "relationships")

_CACHE_TTL_SECONDS = 24 * 3600
_cache: Dict[str, Dict] = {}

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

# Requiring BOTH a relationship keyword nearby AND a corporate-suffix
# pattern in the same sentence is the main false-positive guard --
# either alone matches far too much boilerplate 10-K prose.
_RELATIONSHIP_KEYWORDS = {
    "competitor": re.compile(r"\bcompet(?:e|es|ing|itor|itors|ition)\b", re.I),
    "supplier": re.compile(r"\bsuppliers?\b", re.I),
    "customer": re.compile(r"\bcustomers?\b", re.I),
}

# Matches "Foo Bar Inc.", "Acme Corporation", "Widget & Co., LLC", etc.
# Capped at 5 leading capitalized words to avoid swallowing whole clauses.
_CORP_SUFFIX_RE = re.compile(
    r"\b([A-Z][A-Za-z&.,'\-]*(?:\s+[A-Z][A-Za-z&.,'\-]*){0,4}\s+"
    r"(?:Inc\.?|Incorporated|Corp\.?|Corporation|Company|Co\.|LLC|L\.L\.C\.|"
    r"Ltd\.?|Limited|plc|Group|Holdings|N\.V\.|S\.A\.))\b"
)

# Generic phrases that technically match the corp-suffix regex but are
# never a real third-party company -- excluded so they never leak into
# results (deliberately conservative, expand this list over time rather
# than loosen the regex above).
_GENERIC_EXCLUDE = {
    "the company", "our company", "the group", "the corporation",
    "parent company", "holding company",
}

_MAX_DOC_CHARS = 400_000  # 10-Ks can be huge; cap what we scan for latency/memory
_MAX_MENTIONS = 10


def _init_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sec_business_mentions (
            ticker TEXT NOT NULL,
            filing_date TEXT,
            relationship_hint TEXT,
            entity TEXT,
            sentence TEXT,
            source_url TEXT,
            fetched_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def _load_ticker_cik_map() -> dict:
    """Own copy of the ticker->CIK loader -- see sec_form4_service.py's
    module docstring for why each SEC collector keeps its own copy
    instead of sharing one."""
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
        logger.info("sec_business_text_service: failed to load ticker->CIK map: %s", e)
        return cached or {}


def _latest_10k_filing(cik: str) -> Optional[Dict]:
    """Returns {"accession": "0000320193-24-000123", "primary_document": "aapl-20240928.htm",
    "filing_date": "2024-11-01"} for the most recent 10-K (or 10-K/A), or None."""
    try:
        url = SUBMISSIONS_URL.format(cik10=int(cik))
        res = get_with_backoff(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=20)
        if res.status_code != 200:
            return None
        data = res.json()
        recent = (data.get("filings") or {}).get("recent") or {}
        forms = recent.get("form") or []
        accns = recent.get("accessionNumber") or []
        docs = recent.get("primaryDocument") or []
        dates = recent.get("filingDate") or []
        for i, form in enumerate(forms):
            if form in ("10-K", "10-K/A"):
                if i < len(accns) and i < len(docs):
                    return {
                        "accession": accns[i],
                        "primary_document": docs[i],
                        "filing_date": dates[i] if i < len(dates) else None,
                        "form": form,
                    }
        return None
    except Exception as e:
        logger.info("sec_business_text_service: submissions lookup failed for CIK %s: %s", cik, e)
        return None


def _extract_section(full_text: str, start_pattern: str, end_patterns: List[str]) -> str:
    """Best-effort slice of `full_text` between the LAST occurrence of
    start_pattern (10-Ks often repeat "Item 1" in the table of contents
    before the real section -- the last match is far more often the real
    heading) and the first end_pattern occurring after it. Returns ""
    if the start pattern isn't found (never guesses)."""
    start_matches = list(re.finditer(start_pattern, full_text, re.I))
    if not start_matches:
        return ""
    start = start_matches[-1].end()
    end = len(full_text)
    for pat in end_patterns:
        m = re.search(pat, full_text[start:], re.I)
        if m:
            end = start + m.start()
            break
    return full_text[start:end]


def get_business_relationship_mentions(ticker: str, force_refresh: bool = False) -> Dict:
    """Returns:
        {"available": True, "attribution": "...", "ticker": "AAPL",
         "source_filing": {"form","filing_date","url"},
         "mentions": [{"relationship_hint": "competitor"|"supplier"|"customer",
                        "entity": "Foo Corporation", "sentence": "..."}, ...],
         "method_note": "..."}
        {"available": False, "message": "..."} -- ticker not resolvable to a
        CIK, no 10-K found, the document fetch failed, or the Business/Risk
        Factors sections couldn't be located in the document text. Never
        fabricates a mention list when the real extraction found nothing."""
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return {"available": False, "message": "ticker is required"}

    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(ticker)
    if not force_refresh and cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["result"]

    record_run_start(SOURCE_KEY)
    try:
        cik_map = _load_ticker_cik_map()
        cik = cik_map.get(ticker)
        if not cik:
            result = {"available": False, "message": f"Could not resolve {ticker} to a SEC CIK"}
            _cache[ticker] = {"fetched_at": now, "result": result}
            record_run_error(SOURCE_KEY, "no CIK match")
            return result

        filing = _latest_10k_filing(cik)
        if not filing:
            result = {"available": False, "message": f"No 10-K filing found for {ticker}"}
            _cache[ticker] = {"fetched_at": now, "result": result}
            record_run_error(SOURCE_KEY, "no 10-K found")
            return result

        accession_nodash = filing["accession"].replace("-", "")
        doc_url = FILING_DOC_URL.format(cik=int(cik), accession_nodash=accession_nodash, filename=filing["primary_document"])

        res = get_with_backoff(doc_url, headers={"User-Agent": SEC_USER_AGENT}, timeout=30)
        if res.status_code != 200:
            result = {"available": False, "message": f"Could not fetch 10-K document for {ticker} (HTTP {res.status_code})"}
            _cache[ticker] = {"fetched_at": now, "result": result}
            record_run_error(SOURCE_KEY, f"doc fetch HTTP {res.status_code}")
            return result

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(res.text, "html.parser")
        full_text = soup.get_text(separator=" ")
        full_text = re.sub(r"\s+", " ", full_text)[:_MAX_DOC_CHARS]

        business = _extract_section(
            full_text,
            r"item\s*1\.?\s*business",
            [r"item\s*1a\.?\s*risk\s*factors", r"item\s*2\.?\s*properties"],
        )
        risk_factors = _extract_section(
            full_text,
            r"item\s*1a\.?\s*risk\s*factors",
            [r"item\s*1b\.?", r"item\s*2\.?\s*properties"],
        )
        scope_text = f"{business} {risk_factors}".strip()

        if not scope_text:
            result = {
                "available": False,
                "message": f"Could not locate Item 1/1A section text in {ticker}'s 10-K (document structure not recognized)",
            }
            _cache[ticker] = {"fetched_at": now, "result": result}
            record_run_error(SOURCE_KEY, "sections not found")
            return result

        sentences = re.split(r"(?<=[.!?])\s+", scope_text)
        mentions = []
        seen = set()
        for sentence in sentences:
            if len(sentence) < 20 or len(sentence) > 500:
                continue
            hint = None
            for key, pat in _RELATIONSHIP_KEYWORDS.items():
                if pat.search(sentence):
                    hint = key
                    break
            if not hint:
                continue
            for m in _CORP_SUFFIX_RE.finditer(sentence):
                entity = m.group(1).strip()
                if entity.lower() in _GENERIC_EXCLUDE:
                    continue
                dedup_key = (hint, entity.lower())
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                mentions.append({
                    "relationship_hint": hint,
                    "entity": entity,
                    "sentence": sentence.strip()[:400],
                })
                if len(mentions) >= _MAX_MENTIONS:
                    break
            if len(mentions) >= _MAX_MENTIONS:
                break

        source_filing = {
            "form": filing["form"],
            "filing_date": filing["filing_date"],
            "url": doc_url,
        }

        result = {
            "available": True,
            "attribution": ATTRIBUTION,
            "ticker": ticker,
            "source_filing": source_filing,
            "mentions": mentions,
            "method_note": (
                "Keyword + corporate-suffix pattern matching within the issuer's own "
                "10-K Item 1 (Business) / Item 1A (Risk Factors) text -- not named-entity "
                "recognition, may miss real mentions or occasionally match a phrase that "
                "isn't actually a third-party company. Each result is a literal excerpt, "
                "independently verifiable at source_filing.url."
            ),
        }
        _cache[ticker] = {"fetched_at": now, "result": result}

        try:
            conn = sqlite3.connect(_DB_PATH)
            conn.execute("DELETE FROM sec_business_mentions WHERE ticker = ?", (ticker,))
            for m in mentions:
                conn.execute(
                    "INSERT INTO sec_business_mentions (ticker, filing_date, relationship_hint, entity, sentence, source_url) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (ticker, filing["filing_date"], m["relationship_hint"], m["entity"], m["sentence"], doc_url),
                )
            conn.commit()
            conn.close()
        except Exception:
            pass  # persistence failure must never break the response

        record_run_success(SOURCE_KEY)
        return result
    except Exception as e:
        logger.exception("sec_business_text_service: unexpected failure for %s", ticker)
        result = {"available": False, "message": f"Unexpected error extracting relationships for {ticker}"}
        _cache[ticker] = {"fetched_at": now, "result": result}
        record_run_error(SOURCE_KEY, str(e))
        return result


def get_persisted_mentions(ticker: str, limit: int = 20) -> List[dict]:
    """Read-only, no live fetch -- for the admin panel's history view."""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM sec_business_mentions WHERE ticker=? ORDER BY fetched_at DESC LIMIT ?",
        (ticker.upper().strip(), limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
