"""
FDIC Bank Health Service -- 2026-08-28 (AJ: "咁你一次過起").

Why this fills a real gap: none of the existing Data Factory sources
touch bank-specific balance-sheet health. Confluence Engine and
ai-analysis.html have no way to say "this bank's ROA/equity ratio looks
weak relative to peers" for the handful of publicly-traded banks people
actually look up (JPM, BAC, WFC, C, GS, MS, USB, PNC). FDIC's own
BankFind Suite API publishes exactly this, quarterly, straight from
Call Reports every FDIC-insured bank must file.

Source: FDIC's public BankFind Suite API (banks.data.fdic.gov/api,
redirects to api.fdic.gov/banks/...), free, no key, no registration --
confirmed reachable and returning real data during this build. Fields
used (per FDIC's own data dictionary):
  - ASSET     -- total assets ($ thousands)
  - EQ        -- total equity capital ($ thousands)
  - NETINC    -- net income, quarter ($ thousands)
  - ROA       -- return on assets (%)
  - ROE       -- return on equity (%)
  - REPDTE    -- report date (as of quarter-end) for the figures above

Ticker -> FDIC certificate number mapping: FDIC's own data model keys
each insured institution by a CERT number, not a ticker -- there is no
public ticker field on this API. This module keeps a small explicit
ticker->CERT map for the handful of major publicly-traded bank holding
companies' LEAD BANK subsidiary (e.g. JPMorgan Chase Bank, N.A. for
JPM), same "small explicit table, no fuzzy guessing" convention as
cftc_cot_service.py's _TICKER_TO_CONTRACT and eia_energy_service.py's
_TICKER_TO_SERIES. A ticker not in this table returns None rather than
a guessed match.

Honesty note: a bank holding company's stock (e.g. JPM) legally
represents the WHOLE HOLDING COMPANY, not just the single lead bank
subsidiary FDIC tracks -- this is real bank-level regulatory data, not
consolidated GAAP financials for the ticker (that's what
sec_xbrl_service.py is for, from the same day's build). Presented here
as "lead bank subsidiary health", not "the stock's financials", and
every response says so explicitly.
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

FDIC_BASE_URL = "https://banks.data.fdic.gov/api"
ATTRIBUTION = "Data sourced from the FDIC BankFind Suite API (banks.data.fdic.gov). Not endorsed or certified by the FDIC. Reflects the lead bank subsidiary's Call Report data, not consolidated holding-company financials. For research reference only, not investment advice."

SOURCE_KEY = "fdic_bank_health"
register_source(SOURCE_KEY, "FDIC Bank Health (Lead Subsidiaries)", "banking")

# ticker -> (FDIC certificate number, lead bank subsidiary name)
# CERT numbers verified live against FDIC's own BankFind institution
# search (banks.data.fdic.gov/api/institutions?search=NAME:...) during
# this build, 2026-08-28 -- not guessed. Each is the single ACTIVE:1
# top-scoring "..., National Association"/"Truist Bank" entry for that
# holding company's lead depository subsidiary.
_TICKER_TO_CERT = {
    "JPM": ("628", "JPMorgan Chase Bank, National Association"),
    "BAC": ("3510", "Bank of America, National Association"),
    "WFC": ("3511", "Wells Fargo Bank, National Association"),
    "C": ("7213", "Citibank, National Association"),
    "USB": ("6548", "U.S. Bank National Association"),
    "PNC": ("6384", "PNC Bank, National Association"),
    "TFC": ("9846", "Truist Bank"),
}

_CACHE_TTL_SECONDS = 12 * 3600  # quarterly data -- no need to re-hit more than twice a day
_cache: Dict[str, Dict] = {}  # ticker -> {"fetched_at": epoch, "data": {...}}

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _init_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fdic_bank_health (
            ticker TEXT PRIMARY KEY,
            cert TEXT,
            bank_name TEXT,
            report_date TEXT,
            asset REAL,
            equity REAL,
            net_income REAL,
            roa REAL,
            roe REAL,
            fetched_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def is_available() -> bool:
    return True  # no API key required


def _persist(ticker: str, data: dict):
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            """
            INSERT INTO fdic_bank_health (ticker, cert, bank_name, report_date, asset, equity, net_income, roa, roe, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(ticker) DO UPDATE SET
                cert=excluded.cert, bank_name=excluded.bank_name, report_date=excluded.report_date,
                asset=excluded.asset, equity=excluded.equity, net_income=excluded.net_income,
                roa=excluded.roa, roe=excluded.roe, fetched_at=excluded.fetched_at
            """,
            (ticker, data["cert"], data["bank_name"], data["report_date"], data["asset"],
             data["equity"], data["net_income"], data["roa"], data["roe"]),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("fdic_banking_service: failed to persist %s: %s", ticker, e)


def _load_persisted(ticker: str) -> Optional[dict]:
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM fdic_bank_health WHERE ticker=?", (ticker,)).fetchone()
        conn.close()
        if not row:
            return None
        return {"cert": row["cert"], "bank_name": row["bank_name"], "report_date": row["report_date"],
                "asset": row["asset"], "equity": row["equity"], "net_income": row["net_income"],
                "roa": row["roa"], "roe": row["roe"]}
    except Exception:
        return None


def _fetch_bank(ticker: str) -> Optional[dict]:
    meta = _TICKER_TO_CERT.get(ticker)
    if not meta:
        return None
    cert, bank_name = meta

    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(ticker)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["data"]

    if not is_source_enabled(SOURCE_KEY):
        return cached["data"] if cached else _load_persisted(ticker)

    url = f"{FDIC_BASE_URL}/institutions"
    params = {
        "filters": f"CERT:{cert}",
        "fields": "NAME,CERT,ASSET,EQ,NETINC,ROA,ROE,REPDTE",
        "limit": 1,
    }
    record_run_start(SOURCE_KEY)
    try:
        res = get_with_backoff(url, params=params, timeout=15)
        if res.status_code != 200:
            logger.info("fdic_banking_service: %s (CERT %s) returned HTTP %s", ticker, cert, res.status_code)
            record_run_error(SOURCE_KEY, f"{ticker} (CERT {cert}): HTTP {res.status_code}")
            return cached["data"] if cached else _load_persisted(ticker)
        payload = res.json()
    except Exception as e:
        logger.info("fdic_banking_service: failed to fetch %s: %s", ticker, e)
        record_run_error(SOURCE_KEY, f"{ticker}: {e}")
        return cached["data"] if cached else _load_persisted(ticker)

    rows = payload.get("data") or []
    if not rows:
        record_run_error(SOURCE_KEY, f"{ticker} (CERT {cert}): zero rows returned")
        return cached["data"] if cached else _load_persisted(ticker)

    row = rows[0].get("data") or {}
    data = {
        "cert": cert, "bank_name": row.get("NAME") or bank_name, "report_date": row.get("REPDTE"),
        "asset": row.get("ASSET"), "equity": row.get("EQ"), "net_income": row.get("NETINC"),
        "roa": row.get("ROA"), "roe": row.get("ROE"),
    }
    _cache[ticker] = {"fetched_at": now, "data": data}
    _persist(ticker, data)
    record_run_success(SOURCE_KEY)
    return data


def get_bank_health(ticker: str) -> Optional[Dict]:
    """
    Returns:
        {"available": True, "ticker": "JPM", "attribution": "...",
         "as_of": "...", "bank": {"cert": "628", "bank_name": "...",
             "report_date": "20260630", "asset": ..., "equity": ...,
             "net_income": ..., "roa": ..., "roe": ...}}
        None -- ticker has no FDIC-mapped lead bank subsidiary at all.
    """
    ticker = (ticker or "").upper().strip()
    if ticker not in _TICKER_TO_CERT:
        return None
    data = _fetch_bank(ticker)
    if not data:
        return None
    return {"available": True, "ticker": ticker, "attribution": ATTRIBUTION,
            "as_of": datetime.now(timezone.utc).isoformat(), "bank": data}


def get_snapshot() -> Dict:
    """All watched banks at once, for the admin panel / scheduled refresh
    job -- same shape convention as eia_energy_service.get_snapshot()."""
    banks: Dict[str, Optional[dict]] = {}
    for ticker in _TICKER_TO_CERT:
        result = get_bank_health(ticker)
        banks[ticker] = result["bank"] if result else None

    if all(v is None for v in banks.values()):
        return {"available": False, "message": "FDIC暫時未能提供任何銀行數據（可能係首次運行或短暫故障）。"}

    return {"available": True, "as_of": datetime.now(timezone.utc).isoformat(),
            "attribution": ATTRIBUTION, "banks": banks}


if __name__ == "__main__":
    import json
    print(json.dumps(get_snapshot(), indent=2, ensure_ascii=False))
