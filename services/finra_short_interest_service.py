"""
FINRA Equity Short Interest Service -- 2026-08-27, Data Factory Step 9b
(AJ: second half of the "SEC Form 4 + FINRA短倉" pick).

What this adds: how many shares of a stock are currently sold short is
a genuinely different signal from anything else in this Data Factory --
not positioning in a FUTURES contract (that's cftc_cot_service.py, and
only covers 9 commodity/FX/index contracts, never individual equities),
not institutional 13F/13D ownership, not insider Form 4 activity, but
retail+institutional bearish bets against a specific stock. Read
alongside days-to-cover (short interest ÷ average daily volume), it's
also the classic "short squeeze risk" input.

Source: FINRA's own public short-interest flat files at
cdn.finra.org/equity/otcmarket/biweekly/shrtYYYYMMDD.csv -- genuinely
$0, no API key, no registration (confirmed by browsing FINRA's own
"Equity Short Interest Files" page, which lists these exact URLs as
live downloads through 2026). This is DIFFERENT from FINRA's Query API
(api.finra.org / developer.finra.org), which requires requesting API
Console access through an organization's registered SAA/AA -- that's
effectively member-firm-gated, not a free public signup like FRED/EIA,
so it was deliberately NOT used here. The flat-file path is the
actually-free option.

Reporting schedule (per FINRA's own published Short Interest Reporting
Instructions): settlement dates fall near the 15th and the last
business day of each month, shifted to the preceding business day when
either lands on a weekend/holiday -- there is no fixed formula, so this
module does NOT hardcode a settlement calendar (which would silently go
stale). Instead it generates a small set of CANDIDATE dates (15th and
month-end, walked backward a few days each) and tries them newest-first
until one actually exists on FINRA's CDN, exactly the same "handle
uncertainty by trying, not guessing a hardcoded table" posture as
services/eia_energy_service.py's route corrections this session.

File format: pipe-delimited (despite the .csv extension -- a
well-documented FINRA quirk), one row per security. Column names are
supported defensively across the two schema generations FINRA has used
for this dataset (the older 'equityShortInterest' naming and the
current 'equityShortInterestStandardized' naming) -- same defensive
multi-field-name pattern as cftc_cot_service.py's noncomm_postions_
spread_all typo handling, since this exact header could not be
live-verified from this sandbox.
"""
import csv
import io
import logging
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Optional

from services.outbound_http import get_with_backoff
from services.data_source_registry import (
    register_source, is_source_enabled, record_run_start,
    record_run_success, record_run_error,
)

logger = logging.getLogger(__name__)

SOURCE_KEY = "finra_short_interest"
register_source(SOURCE_KEY, "FINRA Equity Short Interest", "positioning")

FINRA_CSV_URL_TEMPLATE = "https://cdn.finra.org/equity/otcmarket/biweekly/shrt{date}.csv"
ATTRIBUTION = "Data sourced from FINRA's public Equity Short Interest files (cdn.finra.org). Not endorsed or certified by FINRA. For research reference only, not investment advice."

_CACHE_TTL_HOURS = 24  # file only updates biweekly -- this just avoids re-downloading a multi-MB file on every request within a day
_file_cache: Dict = {"settlement_date": None, "fetched_at": None, "rows_by_symbol": None}

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

# Column names tried in order per field -- covers both schema generations
# FINRA has published for this dataset (see module docstring).
_COLUMN_CANDIDATES = {
    "symbol": ["symbolCode", "issueSymbolIdentifier", "symbol"],
    "issue_name": ["issueName", "issuerName", "securityDescription"],
    "current_short": ["currentShortPositionQuantity", "currentShortInterest", "currentShortPosition"],
    "previous_short": ["previousShortPositionQuantity", "previousShortInterest", "previousShortPosition"],
    "avg_daily_volume": ["averageDailyVolumeQuantity", "averageDailyShareVolume", "avgDailyVolume"],
    "days_to_cover": ["daysToCoverQuantity", "daysToCover"],
    "change_pct": ["changePercent", "percentChange", "changePct"],
    "settlement_date": ["settlementDate", "settlementDateTime"],
}


def _init_table():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS finra_short_interest_observations (
            ticker TEXT NOT NULL,
            settlement_date TEXT NOT NULL,
            issue_name TEXT,
            current_short_shares REAL,
            previous_short_shares REAL,
            avg_daily_volume REAL,
            days_to_cover REAL,
            change_pct REAL,
            fetched_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (ticker, settlement_date)
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def _row_get(row: dict, field_key: str) -> Optional[str]:
    for name in _COLUMN_CANDIDATES[field_key]:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def _to_float(raw) -> Optional[float]:
    if raw in (None, ""):
        return None
    try:
        return float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _candidate_settlement_dates(n_months_back: int = 2) -> list:
    """Generates candidate settlement dates (15th and month-end, each
    walked back up to 6 days to land on the actual prior business day
    when the 'ideal' date is a weekend/holiday), newest first. Does NOT
    hardcode an exact settlement calendar -- see module docstring."""
    today = date.today()
    candidates = []
    year, month = today.year, today.month
    for _ in range(n_months_back + 1):
        # month-end
        if month == 12:
            next_month_first = date(year + 1, 1, 1)
        else:
            next_month_first = date(year, month + 1, 1)
        month_end = next_month_first - timedelta(days=1)
        # 15th
        mid_month = date(year, month, 15)
        for anchor in (month_end, mid_month):
            if anchor <= today:
                for back in range(0, 7):
                    d = anchor - timedelta(days=back)
                    if d.weekday() < 5 and d <= today:  # skip weekends, never guess a future date
                        candidates.append(d)
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    seen = set()
    unique_sorted = []
    for d in sorted(candidates, reverse=True):
        if d not in seen:
            seen.add(d)
            unique_sorted.append(d)
    return unique_sorted


def _fetch_latest_file() -> Optional[dict]:
    """Tries candidate settlement dates newest-first, returns
    {"settlement_date": "YYYY-MM-DD", "rows_by_symbol": {SYMBOL: row_dict}}
    for the first one that actually exists on FINRA's CDN, or None if
    every candidate in the search window 404s (e.g. FINRA hasn't
    published this period's file yet, or the URL pattern has changed)."""
    for d in _candidate_settlement_dates():
        url = FINRA_CSV_URL_TEMPLATE.format(date=d.strftime("%Y%m%d"))
        try:
            res = get_with_backoff(url, timeout=30)
        except Exception as e:
            logger.info("finra_short_interest_service: fetch failed for %s: %s", d, e)
            continue
        if res.status_code != 200:
            continue
        try:
            text = res.content.decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(text), delimiter="|")
            rows_by_symbol = {}
            for row in reader:
                symbol = _row_get(row, "symbol")
                if symbol:
                    rows_by_symbol[symbol.upper().strip()] = row
            if rows_by_symbol:
                return {"settlement_date": d.isoformat(), "rows_by_symbol": rows_by_symbol}
        except Exception as e:
            logger.info("finra_short_interest_service: parse failed for %s: %s", d, e)
            continue
    return None


def _persist_row(ticker: str, settlement_date: str, parsed: dict):
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            """
            INSERT INTO finra_short_interest_observations
                (ticker, settlement_date, issue_name, current_short_shares, previous_short_shares,
                 avg_daily_volume, days_to_cover, change_pct, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(ticker, settlement_date) DO UPDATE SET
                issue_name=excluded.issue_name, current_short_shares=excluded.current_short_shares,
                previous_short_shares=excluded.previous_short_shares, avg_daily_volume=excluded.avg_daily_volume,
                days_to_cover=excluded.days_to_cover, change_pct=excluded.change_pct, fetched_at=datetime('now')
            """,
            (ticker, settlement_date, parsed.get("issue_name"), parsed.get("current_short_shares"),
             parsed.get("previous_short_shares"), parsed.get("avg_daily_volume"),
             parsed.get("days_to_cover"), parsed.get("change_pct")),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("finra_short_interest_service: failed to persist %s: %s", ticker, e)


def _load_persisted_latest(ticker: str) -> Optional[dict]:
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        r = conn.execute(
            "SELECT * FROM finra_short_interest_observations WHERE ticker=? ORDER BY settlement_date DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        conn.close()
        return dict(r) if r else None
    except Exception:
        return None


def get_short_interest_for_ticker(ticker: str) -> Dict:
    """
    Returns:
        {"available": True, "attribution": "...", "ticker": "GME",
         "settlement_date": "2026-08-14", "issue_name": "...",
         "current_short_shares": ..., "previous_short_shares": ...,
         "avg_daily_volume": ..., "days_to_cover": ..., "change_pct": ...}
        {"available": False, "message": "..."} -- ticker has no reported
        short position for the latest file (a real, honest "not
        currently shorted at reportable levels" result, not necessarily
        an error), or the file itself couldn't be fetched/parsed at all
        (live AND persisted DB both empty).
    """
    ticker = (ticker or "").upper().strip()
    now = datetime.now(timezone.utc).timestamp()

    if not is_source_enabled(SOURCE_KEY):
        persisted = _load_persisted_latest(ticker)
        return _format_result(ticker, persisted) if persisted else {"available": False, "message": "此來源暫時被管理員停用。"}

    cached = _file_cache
    if not (cached["rows_by_symbol"] and cached["fetched_at"] and (now - cached["fetched_at"]) < _CACHE_TTL_HOURS * 3600):
        record_run_start(SOURCE_KEY)
        fetched = _fetch_latest_file()
        if not fetched:
            record_run_error(SOURCE_KEY, "no candidate settlement-date file could be fetched/parsed")
            persisted = _load_persisted_latest(ticker)
            if persisted:
                return _format_result(ticker, persisted)
            return {"available": False, "message": "FINRA短倉數據暫時未能提供（可能係短暫故障或今期檔案未發布）。"}
        _file_cache.update({"settlement_date": fetched["settlement_date"], "fetched_at": now, "rows_by_symbol": fetched["rows_by_symbol"]})
        record_run_success(SOURCE_KEY)

    row = _file_cache["rows_by_symbol"].get(ticker)
    if not row:
        # Genuinely not in this file -- honest "no reportable short position", not an error.
        persisted = _load_persisted_latest(ticker)
        if persisted:
            return _format_result(ticker, persisted)
        return {"available": False, "message": f"{ticker} 喺最新一期FINRA短倉報告入面冇可報告嘅短倉紀錄。"}

    parsed = {
        "issue_name": _row_get(row, "issue_name"),
        "current_short_shares": _to_float(_row_get(row, "current_short")),
        "previous_short_shares": _to_float(_row_get(row, "previous_short")),
        "avg_daily_volume": _to_float(_row_get(row, "avg_daily_volume")),
        "days_to_cover": _to_float(_row_get(row, "days_to_cover")),
        "change_pct": _to_float(_row_get(row, "change_pct")),
    }
    _persist_row(ticker, _file_cache["settlement_date"], parsed)
    return _format_result(ticker, {"ticker": ticker, "settlement_date": _file_cache["settlement_date"], **parsed})


def _format_result(ticker: str, row: dict) -> Dict:
    return {
        "available": True,
        "attribution": ATTRIBUTION,
        "ticker": ticker,
        "settlement_date": row.get("settlement_date"),
        "issue_name": row.get("issue_name"),
        "current_short_shares": row.get("current_short_shares"),
        "previous_short_shares": row.get("previous_short_shares"),
        "avg_daily_volume": row.get("avg_daily_volume"),
        "days_to_cover": row.get("days_to_cover"),
        "change_pct": row.get("change_pct"),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_short_interest_for_ticker("GME"), indent=2, default=str))
