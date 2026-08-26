"""
CFTC Commitments of Traders (COT) Service -- 2026-08-26, Data Factory
Step 3 (AJ: "混合" FRED + CFTC + SEC EDGAR ownership).

What this is: every Friday, the CFTC (the US derivatives regulator)
publishes how open interest in a futures market splits between
"Commercial" traders (hedgers -- producers/users of the underlying
physical commodity or currency) and "Non-Commercial" traders (large
speculators -- funds). This is the closest free, weekly, no-key-required
signal to "what direction are big funds actually positioned" across
gold, oil, major FX pairs, and equity index futures. It's a genuinely
different data type from anything else in this codebase -- not price,
not sentiment text, not a fundamental ratio, but positioning.

Source: CFTC's own public Socrata Open Data API at
publicreporting.cftc.gov (no API key/token required, rate limits apply
if hammered -- honest User-Agent + backoff via services/outbound_http.py
same as every other collector). Dataset "Legacy - Futures Only"
(id 6dca-aqww) -- chosen over "Disaggregated" or "TFF" variants because
Legacy covers the widest range of contract types (commodities, FX,
financial indices) with the simplest two-way Commercial/Non-Commercial
split, which is enough to answer "are funds net long or net short" for
a first pass. Confirmed field descriptions via CFTC's own "Variable
Names for the Comma Delimited Commitment of Traders Files" page; Socrata
JSON field names are the lowercase/underscored versions of those labels.

Known quirk (confirmed, not guessed): the "All" spreading-position field
has an actual typo in CFTC's own schema -- `noncomm_postions_spread_all`
(missing the "i" in "positions"), unlike the correctly-spelled `_old`/
`_other` variants. This module tries both spellings defensively so a
future CFTC fix to the typo doesn't silently break this collector.

Scope for this MVP: a curated set of 9 major contracts (not all ~200+
CFTC tracks) -- gold, silver, WTI crude, natural gas, EUR/JPY/GBP FX,
E-mini S&P 500, and the 10Y Treasury note. These are the contracts most
relevant to a US-equities-and-macro-focused platform; adding more later
is a one-line addition to _CONTRACTS, no other code changes needed.

Same self-registering + persist-to-SQLite pattern as
services/fred_macro_service.py's migration (Data Factory Step 2) --
see services/data_source_registry.py's docstring for why SQLite/why
self-registration.
"""
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

from services.outbound_http import get_with_backoff
from services.data_source_registry import (
    register_source, is_source_enabled, record_run_start,
    record_run_success, record_run_error,
)

logger = logging.getLogger(__name__)

SOURCE_KEY = "cftc_cot"
register_source(SOURCE_KEY, "CFTC Commitments of Traders (Legacy Futures Only)", "positioning")

COT_BASE_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
ATTRIBUTION = "Data sourced from the CFTC's public Commitments of Traders report (publicreporting.cftc.gov). Not endorsed or certified by the CFTC."

# CFTC contract market codes -- confirmed against CFTC/Tradingster COT
# report pages, not guessed. label is for display; asset_hint is a loose
# tie-in for callers that want to map this to an equity/macro theme
# (e.g. gold COT positioning as a risk-sentiment proxy).
_CONTRACTS = {
    "088691": {"label": "Gold (COMEX)", "category": "metals"},
    "084691": {"label": "Silver (COMEX)", "category": "metals"},
    "067651": {"label": "WTI Crude Oil (NYMEX)", "category": "energy"},
    "023651": {"label": "Natural Gas (NYMEX)", "category": "energy"},
    "099741": {"label": "EUR/USD (CME)", "category": "fx"},
    "097741": {"label": "JPY/USD (CME)", "category": "fx"},
    "096742": {"label": "GBP/USD (CME)", "category": "fx"},
    "13874A": {"label": "E-mini S&P 500 (CME)", "category": "equity_index"},
    "043602": {"label": "10-Year US Treasury Note (CBOT)", "category": "rates"},
}

_CACHE_TTL_SECONDS = 6 * 3600  # COT only updates weekly; this just avoids re-hitting CFTC on every page load within a session
_cache: Dict[str, Dict] = {}  # contract_code -> {"fetched_at": epoch, "row": {...}}

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _init_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cftc_cot_observations (
            contract_code TEXT NOT NULL,
            label TEXT,
            category TEXT,
            report_date TEXT NOT NULL,
            open_interest INTEGER,
            noncomm_long INTEGER,
            noncomm_short INTEGER,
            noncomm_spread INTEGER,
            comm_long INTEGER,
            comm_short INTEGER,
            net_noncomm INTEGER,
            net_comm INTEGER,
            fetched_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (contract_code, report_date)
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def _to_int(row: dict, *field_names) -> Optional[int]:
    """Tries each field name in order (handles the noncomm_postions_
    spread_all typo defensively) -- returns None (never 0) if the field
    is genuinely absent, consistent with this codebase's honesty
    contract of never fabricating a value for missing data."""
    for name in field_names:
        raw = row.get(name)
        if raw not in (None, ""):
            try:
                return int(float(raw))
            except (TypeError, ValueError):
                continue
    return None


def _fetch_latest_row(contract_code: str) -> Optional[dict]:
    """Returns the single most recent COT report row for this contract,
    or None if unavailable from live fetch, cache, or persisted DB."""
    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(contract_code)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["row"]

    if not is_source_enabled(SOURCE_KEY):
        return (cached["row"] if cached else None) or _load_persisted_latest(contract_code)

    params = {
        "cftc_contract_market_code": contract_code,
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": 1,
    }
    record_run_start(SOURCE_KEY)
    try:
        res = get_with_backoff(COT_BASE_URL, params=params, timeout=15)
        if res.status_code != 200:
            logger.info("cftc_cot_service: %s returned HTTP %s", contract_code, res.status_code)
            record_run_error(SOURCE_KEY, f"{contract_code}: HTTP {res.status_code}")
            return (cached["row"] if cached else None) or _load_persisted_latest(contract_code)
        payload = res.json()
    except Exception as e:
        logger.info("cftc_cot_service: failed to fetch %s: %s", contract_code, e)
        record_run_error(SOURCE_KEY, f"{contract_code}: {e}")
        return (cached["row"] if cached else None) or _load_persisted_latest(contract_code)

    if not payload:
        record_run_error(SOURCE_KEY, f"{contract_code}: empty response")
        return (cached["row"] if cached else None) or _load_persisted_latest(contract_code)

    raw = payload[0]
    report_date = raw.get("report_date_as_yyyy_mm_dd", "")[:10]
    meta = _CONTRACTS.get(contract_code, {})
    row = {
        "contract_code": contract_code,
        "label": meta.get("label", contract_code),
        "category": meta.get("category"),
        "report_date": report_date,
        "open_interest": _to_int(raw, "open_interest_all"),
        "noncomm_long": _to_int(raw, "noncomm_positions_long_all"),
        "noncomm_short": _to_int(raw, "noncomm_positions_short_all"),
        "noncomm_spread": _to_int(raw, "noncomm_postions_spread_all", "noncomm_positions_spread_all"),
        "comm_long": _to_int(raw, "comm_positions_long_all"),
        "comm_short": _to_int(raw, "comm_positions_short_all"),
    }
    if row["noncomm_long"] is not None and row["noncomm_short"] is not None:
        row["net_noncomm"] = row["noncomm_long"] - row["noncomm_short"]
    else:
        row["net_noncomm"] = None
    if row["comm_long"] is not None and row["comm_short"] is not None:
        row["net_comm"] = row["comm_long"] - row["comm_short"]
    else:
        row["net_comm"] = None

    if not report_date:
        record_run_error(SOURCE_KEY, f"{contract_code}: no report_date in response")
        return (cached["row"] if cached else None) or _load_persisted_latest(contract_code)

    _cache[contract_code] = {"fetched_at": now, "row": row}
    _persist_row(row)
    record_run_success(SOURCE_KEY)
    return row


def _persist_row(row: dict):
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            """
            INSERT INTO cftc_cot_observations
                (contract_code, label, category, report_date, open_interest,
                 noncomm_long, noncomm_short, noncomm_spread, comm_long, comm_short,
                 net_noncomm, net_comm, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(contract_code, report_date) DO UPDATE SET
                open_interest=excluded.open_interest,
                noncomm_long=excluded.noncomm_long,
                noncomm_short=excluded.noncomm_short,
                noncomm_spread=excluded.noncomm_spread,
                comm_long=excluded.comm_long,
                comm_short=excluded.comm_short,
                net_noncomm=excluded.net_noncomm,
                net_comm=excluded.net_comm,
                fetched_at=datetime('now')
            """,
            (
                row["contract_code"], row["label"], row["category"], row["report_date"],
                row["open_interest"], row["noncomm_long"], row["noncomm_short"], row["noncomm_spread"],
                row["comm_long"], row["comm_short"], row["net_noncomm"], row["net_comm"],
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("cftc_cot_service: failed to persist %s: %s", row.get("contract_code"), e)


def _load_persisted_latest(contract_code: str) -> Optional[dict]:
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        r = conn.execute(
            "SELECT * FROM cftc_cot_observations WHERE contract_code=? ORDER BY report_date DESC LIMIT 1",
            (contract_code,),
        ).fetchone()
        conn.close()
        return dict(r) if r else None
    except Exception:
        return None


def get_snapshot() -> Dict:
    """
    Returns:
        {"available": True, "as_of": "...", "attribution": "...",
         "contracts": {
            "088691": {"label": "Gold (COMEX)", "report_date": "2026-08-19",
                       "net_noncomm": 145230, "net_comm": -138900, ...},
            ...
         }}
        {"available": False, "message": "..."} if every contract fetch
        failed (live, cache, AND persisted DB all empty -- e.g. very
        first run ever, before any successful fetch has happened).

    net_noncomm > 0 means speculators (funds) are net long; net_comm is
    the mirror-image hedger side and is structurally the near-opposite
    of net_noncomm (commercials are the other side of most speculative
    trades) -- both are surfaced since the SPREAD between them, not
    either number alone, is what most COT-based analysis actually reads.
    """
    contracts: Dict[str, Optional[dict]] = {}
    for code in _CONTRACTS:
        row = _fetch_latest_row(code)
        contracts[code] = row

    if all(v is None for v in contracts.values()):
        return {"available": False, "message": "CFTC COT暫時未能提供任何合約數據（可能係首次運行或短暫故障）。"}

    return {
        "available": True,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "attribution": ATTRIBUTION,
        "contracts": contracts,
    }


def get_contract(contract_code: str) -> Optional[Dict]:
    """Single-contract lookup, e.g. for a ticker-specific page that wants
    just gold or just the S&P 500 e-mini COT reading."""
    if contract_code not in _CONTRACTS:
        return None
    return _fetch_latest_row(contract_code)


if __name__ == "__main__":
    import json
    print(json.dumps(get_snapshot(), indent=2, ensure_ascii=False))
