"""
SEC Form 4 Insider Trading Service -- 2026-08-27, Data Factory Step 9a
(AJ: after the EIA/Treasury/Coinbase batch, asked to pick the next
source; chose "SEC Form 4 內幕人交易" -- insider trading -- alongside
FINRA short interest).

What this completes: services/sec_ownership_service.py (13F, quarterly
institutional positions) and services/sec_13d_13g_service.py (13D/13G,
event-driven 5%+ ownership crossings) cover two of the three real SEC
ownership signal types. Form 4 is the third and arguably most direct
one -- it's filed by a company's OWN directors, officers, and 10%+
owners within 2 business days of them buying or selling their own
company's stock. Unlike 13F (a snapshot of what a fund holds, filed up
to 45 days late) or 13D/13G (ownership crossing a 5% threshold), Form 4
is the closest thing to "does the person who actually runs this company
believe in it enough to buy more, or are they cashing out" -- a
genuinely different, faster, and more personal signal than either of
the other two.

Source: SEC EDGAR, same $0/no-key/honest-User-Agent discipline as every
other SEC collector here. Two-hop pipeline, same shape as sec_ownership_
service.py's 13F pipeline:
  1. Resolve ticker -> CIK via SEC's own company_tickers.json (own copy
     of the loader, kept separate from sec_ownership_service.py's --
     that one deliberately drops the CIK field it doesn't need; this
     one needs it, so a shared helper would have to grow a parameter
     just for this caller. Same "don't couple two modules with
     different needs" reasoning documented in sec_13d_13g_service.py).
  2. List recent Form 4 filings FOR THAT ISSUER (not filed BY it -- Form
     4s are filed by the insider, but EDGAR's company browse endpoint
     cross-indexes them under the issuer's own CIK when owner=include)
     via the browse-edgar CGI endpoint's Atom output. This is a
     different EDGAR surface than submissions.json (which only lists
     filings the CIK itself is the FILER of) -- confirmed necessary
     because data.sec.gov/submissions never lists insider filings under
     an issuer's own CIK.
  3. For each recent filing, fetch its directory index.json (same
     pattern as sec_ownership_service.py's _find_infotable_filename)
     and parse the ownership XML -- a stable, decades-old SEC schema
     (ownershipDocument -> reportingOwner + nonDerivativeTable ->
     nonDerivativeTransaction), NOT the fragile per-filer-software
     naming variance that caused the Berkshire 13F bug (Form 4's XML
     data file is essentially always literally named primary_doc.xml
     for anything filed electronically since ~2003, since Form 4 has no
     separate "information table" the way 13F does).

Honesty note on verification (same standard as every other SEC module
here): the ownership XML schema itself is verified against SEC's own
published Form 4 XML Technical Specification. The Atom feed shape from
browse-edgar (step 2) is verified against well-documented, widely-used
EDGAR crawler conventions but could NOT be live-tested from this sandbox
(sec.gov's CGI endpoints have consistently timed out from here for
every SEC collector built this batch -- confirmed not sandbox-specific
by every other SEC source in this codebase working fine once deployed
to Railway). First production run must be watched via the Data Factory
admin panel + /admin/sec-form4-debug for exactly this reason.

Transaction codes (SEC's own fixed list, "Explanation of Responses" on
every Form 4): only a curated few are labeled for display -- an
unrecognized code is shown as-is rather than guessed at.
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

SOURCE_KEY = "sec_form4_insider"
register_source(SOURCE_KEY, "SEC Form 4 Insider Trading", "ownership")

SEC_USER_AGENT = "XFINLABBot/1.0 (+https://www.xfinlab.com; contact: support@xfinlab.com)"
ATTRIBUTION = "Data sourced from SEC EDGAR Form 4 filings. Not endorsed or certified by the SEC. For research reference only, not investment advice."

TICKER_CIK_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_TICKER_CIK_CACHE_TTL_DAYS = 7
_ticker_cik_cache = {"data": None, "fetched_at": None}

BROWSE_EDGAR_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
FILING_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/index.json"
FILING_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{filename}"

_LOOKUP_CACHE_TTL_HOURS = 24  # insider filings are event-driven, not continuous -- same TTL as sec_13d_13g_service.py
_LOOKBACK_FILINGS = 5  # most recent N Form 4 filings for this issuer -- caps the worst-case per-ticker latency (each filing costs 2 more HTTP hops)
_cache: Dict[str, Dict] = {}  # ticker -> {"fetched_at": epoch, "result": {...}}

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

# SEC's own fixed transaction-code list (Form 4 "Table I/II, Column 3" +
# instructions) -- only the common ones get a human label; anything else
# is shown as its raw code rather than guessed at.
_TRANSACTION_CODE_LABELS = {
    "P": "Open market purchase",
    "S": "Open market sale",
    "A": "Grant/award",
    "D": "Disposition to issuer",
    "F": "Tax withholding (shares delivered)",
    "M": "Option exercise",
    "G": "Gift",
    "C": "Conversion of derivative",
    "V": "Transaction voluntarily reported earlier than required",
}


def _init_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sec_form4_transactions (
            accession TEXT NOT NULL,
            line_no INTEGER NOT NULL,
            ticker TEXT,
            issuer_cik TEXT,
            insider_name TEXT,
            insider_cik TEXT,
            is_director INTEGER,
            is_officer INTEGER,
            is_ten_percent_owner INTEGER,
            officer_title TEXT,
            transaction_date TEXT,
            transaction_code TEXT,
            shares REAL,
            price_per_share REAL,
            acquired_disposed TEXT,
            shares_owned_after REAL,
            filed_at TEXT,
            fetched_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (accession, line_no)
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def _strip_ns(tag: str) -> str:
    """Same namespace-agnostic tag matching as sec_ownership_service.py's
    13F parser -- Form 4 XML is unnamespaced in practice, but this costs
    nothing and protects against SEC ever changing that."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _fetch_json(url: str, params: dict = None):
    res = get_with_backoff(url, params=params, headers={"User-Agent": SEC_USER_AGENT}, timeout=20)
    if res.status_code != 200:
        raise RuntimeError(f"HTTP {res.status_code} for {url}")
    return res.json()


def _load_ticker_cik_map() -> dict:
    """Own copy of the ticker->CIK loader -- see module docstring for why
    this isn't shared with sec_ownership_service.py's ticker->title map
    (that one deliberately drops the CIK field this caller needs)."""
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
        logger.info("sec_form4_service: ticker->CIK map fetch failed: %s", e)
        return cached or {}


def _list_recent_form4_filings(cik: str, limit: int = _LOOKBACK_FILINGS) -> List[dict]:
    """Returns [{"accession_nodash": "...", "insider_name": "...",
    "insider_cik": "...", "filed_date": "YYYY-MM-DD"}, ...] for the most
    recent Form 4 filings cross-indexed under this ISSUER's CIK
    (owner=include is what makes browse-edgar return insider filings
    about a company, not just filings the company itself made -- see
    module docstring). Atom entries are parsed defensively (regex over
    <title>/<id>/<summary> text, tag-matched namespace-agnostically) since
    this exact feed shape could not be live-verified from this sandbox."""
    params = {
        "action": "getcompany", "CIK": cik, "type": "4",
        "dateb": "", "owner": "include", "count": limit, "output": "atom",
    }
    res = get_with_backoff(BROWSE_EDGAR_URL, params=params, headers={"User-Agent": SEC_USER_AGENT}, timeout=20)
    if res.status_code != 200:
        raise RuntimeError(f"HTTP {res.status_code} for browse-edgar (CIK {cik})")

    root = ET.fromstring(res.content)
    filings = []
    for entry in root:
        if _strip_ns(entry.tag) != "entry":
            continue
        title_text, id_text, summary_text, updated_text = "", "", "", ""
        for child in entry:
            local = _strip_ns(child.tag)
            if local == "title":
                title_text = child.text or ""
            elif local == "id":
                id_text = child.text or ""
            elif local == "summary":
                summary_text = child.text or ""
            elif local == "updated":
                updated_text = child.text or ""

        accession_match = re.search(r"accession-number=([\d-]+)", id_text)
        if not accession_match:
            continue  # can't do anything without an accession number -- skip this entry rather than guess
        accession_nodash = accession_match.group(1).replace("-", "")

        name_match = re.match(r"^4\s*-\s*(.+?)\s*\((\d+)\)", title_text.strip())
        insider_name = name_match.group(1).strip() if name_match else None
        insider_cik = name_match.group(2) if name_match else None

        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", summary_text) or re.search(r"(\d{4}-\d{2}-\d{2})", updated_text)
        filed_date = date_match.group(1) if date_match else None

        filings.append({
            "accession_nodash": accession_nodash,
            "insider_name": insider_name,
            "insider_cik": insider_cik,
            "filed_date": filed_date,
        })
    return filings


def _find_ownership_xml_filename(cik: str, accession_nodash: str) -> Optional[str]:
    """Form 4's data file is almost always literally 'primary_doc.xml'
    (unlike 13F, Form 4 has no separate information-table file -- the
    cover page AND the transaction data are the same document). Same
    3-strategy defensive fallback as sec_ownership_service.py's 13F
    infotable detection, in case a filing doesn't follow the common
    case: (1) filename is exactly primary_doc.xml, (2) directory item
    type mentions '4' or 'OWNERSHIP', (3) exactly one XML file in the
    directory at all."""
    idx = _fetch_json(FILING_INDEX_URL.format(cik=cik, accession_nodash=accession_nodash))
    items = ((idx.get("directory") or {}).get("item")) or []

    for item in items:
        if item.get("name", "").lower() == "primary_doc.xml":
            return item["name"]

    for item in items:
        fname = item.get("name", "")
        item_type = str(item.get("type", "")).upper()
        if fname.lower().endswith(".xml") and ("OWNERSHIP" in item_type or item_type == "4"):
            return fname

    xml_items = [item.get("name", "") for item in items if item.get("name", "").lower().endswith(".xml")]
    if len(xml_items) == 1:
        return xml_items[0]

    return None


def _text(el, local_name) -> Optional[str]:
    """Finds the first descendant with this local tag name (namespace-
    agnostic) and returns its text -- or, if that element itself has no
    direct text (SEC's Form 4 schema wraps most fields one level deeper,
    e.g. <transactionShares><value>50000</value></transactionShares>,
    while a few like <transactionCode>S</transactionCode> are flat),
    the text of its own nested <value> child instead. Returns None if
    neither has usable text."""
    for child in el.iter():
        if _strip_ns(child.tag) != local_name:
            continue
        direct = (child.text or "").strip()
        if direct:
            return direct
        for grandchild in child:
            if _strip_ns(grandchild.tag) == "value":
                nested = (grandchild.text or "").strip()
                if nested:
                    return nested
        return None
    return None


def _parse_ownership_xml(xml_bytes: bytes) -> dict:
    """Parses one Form 4 ownershipDocument into
    {"insider_name", "is_director", "is_officer", "is_ten_percent_owner",
     "officer_title", "transactions": [{"transaction_date",
     "transaction_code", "shares", "price_per_share", "acquired_disposed",
     "shares_owned_after"}, ...]}.

    Only reads nonDerivativeTransaction rows (actual stock buys/sells) --
    derivativeTransaction (options/RSUs being granted or exercised) is a
    real signal too but a structurally different table this MVP doesn't
    parse yet, to avoid conflating "sold stock on the open market" with
    "was granted options as compensation" under one number.
    """
    root = ET.fromstring(xml_bytes)

    owner_name = None
    is_director = is_officer = is_ten_percent_owner = False
    officer_title = None
    for el in root.iter():
        local = _strip_ns(el.tag)
        if local == "rptOwnerName" and owner_name is None:
            owner_name = (el.text or "").strip() or None
        elif local == "isDirector":
            is_director = (el.text or "").strip() == "1"
        elif local == "isOfficer":
            is_officer = (el.text or "").strip() == "1"
        elif local == "isTenPercentOwner":
            is_ten_percent_owner = (el.text or "").strip() == "1"
        elif local == "officerTitle" and officer_title is None:
            officer_title = (el.text or "").strip() or None

    transactions = []
    for el in root.iter():
        if _strip_ns(el.tag) != "nonDerivativeTransaction":
            continue
        try:
            shares = float(_text(el, "transactionShares") or "")
        except (TypeError, ValueError):
            shares = None
        try:
            price = float(_text(el, "transactionPricePerShare") or "")
        except (TypeError, ValueError):
            price = None  # some codes (e.g. gifts) legitimately have no price -- not a parse failure
        try:
            shares_after = float(_text(el, "sharesOwnedFollowingTransaction") or "")
        except (TypeError, ValueError):
            shares_after = None

        transactions.append({
            "transaction_date": _text(el, "transactionDate"),
            "transaction_code": _text(el, "transactionCode"),
            "shares": shares,
            "price_per_share": price,
            "acquired_disposed": _text(el, "transactionAcquiredDisposedCode"),
            "shares_owned_after": shares_after,
        })

    return {
        "insider_name": owner_name,
        "is_director": is_director,
        "is_officer": is_officer,
        "is_ten_percent_owner": is_ten_percent_owner,
        "officer_title": officer_title,
        "transactions": transactions,
    }


def _persist_transactions(accession: str, ticker: str, issuer_cik: str, filed_date: Optional[str], parsed: dict):
    if not parsed.get("transactions"):
        return
    try:
        conn = sqlite3.connect(_DB_PATH)
        rows = [
            (
                accession, i, ticker, issuer_cik,
                parsed["insider_name"], None,
                int(parsed["is_director"]), int(parsed["is_officer"]), int(parsed["is_ten_percent_owner"]),
                parsed["officer_title"],
                t["transaction_date"], t["transaction_code"], t["shares"], t["price_per_share"],
                t["acquired_disposed"], t["shares_owned_after"], filed_date,
            )
            for i, t in enumerate(parsed["transactions"])
        ]
        conn.executemany(
            """
            INSERT INTO sec_form4_transactions
                (accession, line_no, ticker, issuer_cik, insider_name, insider_cik,
                 is_director, is_officer, is_ten_percent_owner, officer_title,
                 transaction_date, transaction_code, shares, price_per_share,
                 acquired_disposed, shares_owned_after, filed_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(accession, line_no) DO UPDATE SET fetched_at=datetime('now')
            """,
            rows,
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("sec_form4_service: failed to persist %s: %s", accession, e)


def _load_persisted(ticker: str) -> List[dict]:
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM sec_form4_transactions WHERE ticker=? ORDER BY transaction_date DESC, accession DESC LIMIT 30",
            (ticker,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_recent_insider_transactions(ticker: str, force_refresh: bool = False) -> Dict:
    """
    Returns:
        {"available": True, "attribution": "...", "ticker": "AAPL",
         "transactions": [{"insider_name", "officer_title", "is_director",
             "is_officer", "is_ten_percent_owner", "transaction_date",
             "transaction_code", "transaction_label", "shares",
             "price_per_share", "acquired_disposed", "shares_owned_after"}, ...],
         "summary": {"buy_count": N, "sell_count": N,
             "net_shares": ..., "net_value_usd": ...}}
        {"available": False, "message": "..."} -- ticker not resolvable
        to a CIK, or every filing fetch failed (live AND persisted DB
        both empty).

    `transactions` covers only non-derivative (actual open-market/direct
    stock) transactions from the most recent _LOOKBACK_FILINGS Form 4
    filings -- NOT a complete trading history, and NOT derivative
    (option/RSU) activity. summary's net_value_usd only sums rows that
    have both a price and share count (gifts/some grants don't) -- never
    fabricates a price for those.
    """
    ticker = (ticker or "").upper().strip()
    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(ticker)
    if not force_refresh and cached and (now - cached["fetched_at"]) < _LOOKUP_CACHE_TTL_HOURS * 3600:
        return cached["result"]

    cik_map = _load_ticker_cik_map()
    cik = cik_map.get(ticker)
    if not cik:
        return {"available": False, "message": f"{ticker} 唔喺SEC EDGAR嘅美股公司名單入面（可能唔係美股）。"}

    if not is_source_enabled(SOURCE_KEY):
        persisted = _load_persisted(ticker)
        return (cached["result"] if cached else None) or (_format_result(ticker, persisted) if persisted else {"available": False, "message": "此來源暫時被管理員停用。"})

    record_run_start(SOURCE_KEY)
    try:
        filings = _list_recent_form4_filings(cik)
    except Exception as e:
        record_run_error(SOURCE_KEY, f"{ticker}: filing list fetch failed: {e}")
        persisted = _load_persisted(ticker)
        return (cached["result"] if cached else None) or (_format_result(ticker, persisted) if persisted else {"available": False, "message": "SEC暫時未能回應（可能係短暫故障）。"})

    all_rows = []
    any_success = False
    for filing in filings:
        try:
            fname = _find_ownership_xml_filename(cik, filing["accession_nodash"])
            if not fname:
                continue
            doc_res = get_with_backoff(
                FILING_DOC_URL.format(cik=cik, accession_nodash=filing["accession_nodash"], filename=fname),
                headers={"User-Agent": SEC_USER_AGENT}, timeout=20,
            )
            if doc_res.status_code != 200:
                continue
            parsed = _parse_ownership_xml(doc_res.content)
            if not parsed.get("transactions"):
                continue
            any_success = True
            _persist_transactions(filing["accession_nodash"], ticker, cik, filing.get("filed_date"), parsed)
            for t in parsed["transactions"]:
                all_rows.append({
                    "insider_name": parsed["insider_name"] or filing.get("insider_name"),
                    "officer_title": parsed["officer_title"],
                    "is_director": parsed["is_director"],
                    "is_officer": parsed["is_officer"],
                    "is_ten_percent_owner": parsed["is_ten_percent_owner"],
                    "transaction_date": t["transaction_date"] or filing.get("filed_date"),
                    "transaction_code": t["transaction_code"],
                    "shares": t["shares"],
                    "price_per_share": t["price_per_share"],
                    "acquired_disposed": t["acquired_disposed"],
                    "shares_owned_after": t["shares_owned_after"],
                })
        except Exception as e:
            logger.info("sec_form4_service: failed to process filing %s for %s: %s", filing.get("accession_nodash"), ticker, e)
            continue

    if not any_success:
        record_run_error(SOURCE_KEY, f"{ticker}: no Form 4 filings could be parsed ({len(filings)} candidates)")
        persisted = _load_persisted(ticker)
        if persisted:
            result = _format_result(ticker, persisted)
            _cache[ticker] = {"fetched_at": now, "result": result}
            return result
        return {"available": False, "message": "此股票暫時未有可解讀嘅Form 4內幕人交易記錄。"}

    record_run_success(SOURCE_KEY)
    all_rows.sort(key=lambda r: r.get("transaction_date") or "", reverse=True)
    result = _format_result(ticker, all_rows)
    _cache[ticker] = {"fetched_at": now, "result": result}
    return result


def _format_result(ticker: str, rows: List[dict]) -> Dict:
    transactions = []
    buy_count = sell_count = 0
    net_shares = 0.0
    net_value_usd = 0.0
    for r in rows[:30]:
        code = r.get("transaction_code")
        transactions.append({**r, "transaction_label": _TRANSACTION_CODE_LABELS.get(code, code)})
        acquired = r.get("acquired_disposed") == "A"
        if code == "P":
            buy_count += 1
        elif code == "S":
            sell_count += 1
        shares = r.get("shares")
        price = r.get("price_per_share")
        if shares is not None:
            net_shares += shares if acquired else -shares
            if price is not None:
                net_value_usd += (shares * price) if acquired else -(shares * price)

    return {
        "available": True,
        "attribution": ATTRIBUTION,
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "transactions": transactions,
        "summary": {
            "buy_count": buy_count,
            "sell_count": sell_count,
            "net_shares": round(net_shares, 2),
            "net_value_usd": round(net_value_usd, 2),
        },
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_recent_insider_transactions("AAPL"), indent=2, default=str))
