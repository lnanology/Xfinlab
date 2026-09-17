"""
Point-in-Time / Vintage Data Store -- 2026-09-17 (AJ: "Point-in-time/vintage
data質量呢個engineering項目，做啦" -- greenlit after a real r/quant comment
from "VettaQ" on AJ's XFINLAB post called out that a serious backtesting API
needs (a) an AVAILABILITY timestamp per data point, not just the period it
describes, and (b) immutable VINTAGES so a later restatement never silently
overwrites what was actually knowable on an earlier date).

The problem this fixes (confirmed to be real, not assumed -- see the
fred_macro_service.py module comment and sec_ownership_service.py's
`filing_dates` field, both of which admit/show that today's XFINLAB has
no point-in-time serving anywhere):

  Every existing collector in this codebase (sec_xbrl_service.py,
  fred_macro_service.py, sec_ownership_service.py, etc.) stores "the best
  known value for period X" and overwrites it in place whenever a fresher
  fetch comes in. That's fine for a live dashboard. It is WRONG for a
  backtest: a strategy that queries "Q2 2024 revenue" and gets whatever
  SEC's CURRENT number is would be using information that did not exist
  on the trade date it's supposedly evaluating -- classic look-ahead bias.
  A 10-K filed 2024-08-15 is not knowable on 2024-07-01, and if that 10-K
  is later amended (10-K/A), the ORIGINAL as-filed number -- not the
  amendment -- is what a same-day trader actually saw.

What this module does NOT try to do:
  - It does not replace any existing service's live/current-value cache
    (sec_xbrl_service.py's `sec_xbrl_facts` table, etc. keep working
    exactly as before). This is a strictly additive, opt-in layer that a
    collector can call alongside its existing persistence.
  - It does not backfill history retroactively -- vintages only start
    accumulating from the first call to record_observation() going
    forward. A ticker with no prior ingestion has no PIT history yet;
    callers must treat "no rows" as "unknown", never as "zero".
  - It does not use a market-holiday calendar for the availability
    buffer -- only weekends are skipped. A NYSE holiday landing inside
    the buffer window means available_at could be off by one trading
    day. Documented here rather than silently assumed correct; fine for
    an initial cut, worth revisiting if this is used for anything
    latency-sensitive.

Design (mirrors the self-registering, opt-in, "never touch what's not
opted in" pattern already established by data_source_registry.py):
  - One shared, generic SQLite table (`pit_observations`), keyed by
    (source_key, entity_key, concept_key, period_end, filed_date) so the
    same module serves ANY collector (SEC XBRL, FRED, ownership, etc.),
    not just one.
  - `record_observation()` is called by a collector right after it
    fetches a fresh value. It is entirely best-effort/never-raises --
    exactly like record_run_error() in data_source_registry.py, a
    failure here must never break the collector's existing live path.
  - Each (source, entity, concept, period, filed_date) combination is
    inserted AT MOST ONCE (ON CONFLICT DO NOTHING). A restatement shows
    up as a NEW row because it has a new filed_date -- the old row is
    never touched. This is what makes history "vintage-safe": nothing
    is ever overwritten, only added to.
  - `get_latest_value_as_of()` is the actual anti-look-ahead query: "as
    of as_of_date, what's the most recently-available value for this
    concept, regardless of which period it covers" -- the query a
    correct backtest should run instead of "give me the current value".
"""
import logging
import os
import sqlite3
from datetime import date, datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

_DEFAULT_BUFFER_BUSINESS_DAYS = 2  # SEC filings typically post to EDGAR same-day, but
# give a small buffer for realistic "when could a human/system actually have ingested
# this" -- matches the buffer VettaQ's comment described as standard backtesting practice.


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pit_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_key TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            concept_key TEXT NOT NULL,
            period_end TEXT,
            value REAL,
            unit TEXT,
            form TEXT,
            filed_date TEXT NOT NULL,
            available_at TEXT NOT NULL,
            recorded_at TEXT DEFAULT (datetime('now')),
            UNIQUE(source_key, entity_key, concept_key, period_end, filed_date)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_pit_lookup
        ON pit_observations (source_key, entity_key, concept_key, available_at)
    """)
    conn.commit()
    conn.close()


_init_table()


def _add_business_days(start: date, days: int) -> date:
    """Skips weekends only -- see module docstring's honesty note about
    not having a market-holiday calendar wired in yet."""
    d = start
    added = 0
    while added < days:
        d += timedelta(days=1)
        if d.weekday() < 5:  # Mon=0 ... Fri=4
            added += 1
    return d


def record_observation(
    source_key: str,
    entity_key: str,
    concept_key: str,
    value: float,
    unit: Optional[str],
    period_end: Optional[str],
    filed_date: str,
    form: Optional[str] = None,
    buffer_business_days: int = _DEFAULT_BUFFER_BUSINESS_DAYS,
) -> bool:
    """Records one immutable vintage. Best-effort -- logs and returns
    False on any failure rather than raising, so a caller's existing
    (non-PIT) persistence path is never put at risk by this optional
    extra layer.

    filed_date must be an ISO "YYYY-MM-DD" string -- the actual date the
    filing/observation became public, NOT the period it describes. If a
    collector cannot determine a real filed date, it should not call
    this function at all rather than guessing (guessing would silently
    poison the anti-look-ahead guarantee this whole store exists for).

    Returns True if a NEW vintage row was inserted, False if this exact
    (source, entity, concept, period, filed_date) combination was
    already recorded (not an error -- just means nothing changed) or if
    recording failed.
    """
    try:
        filed = datetime.strptime(filed_date, "%Y-%m-%d").date()
    except (ValueError, TypeError) as e:
        logger.info("point_in_time_store: bad filed_date %r for %s/%s/%s: %s",
                    filed_date, source_key, entity_key, concept_key, e)
        return False

    available_at = _add_business_days(filed, buffer_business_days).isoformat()
    try:
        conn = _get_conn()
        cur = conn.execute(
            """INSERT INTO pit_observations
                (source_key, entity_key, concept_key, period_end, value, unit, form, filed_date, available_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(source_key, entity_key, concept_key, period_end, filed_date) DO NOTHING""",
            (source_key, entity_key, concept_key, period_end, value, unit, form, filed_date, available_at),
        )
        conn.commit()
        inserted = cur.rowcount > 0
        conn.close()
        return inserted
    except Exception as e:
        logger.info("point_in_time_store: failed to record %s/%s/%s: %s",
                    source_key, entity_key, concept_key, e)
        return False


def get_value_as_of(source_key: str, entity_key: str, concept_key: str,
                     period_end: str, as_of_date: str) -> Optional[dict]:
    """For ONE specific period_end (e.g. "as of 2025-03-01, what did we
    know about fiscal-year-2024 revenue") -- useful for restatement
    analysis ("how did our knowledge of this exact period change over
    time"). For backtesting "what's the latest fundamentals figure I
    could have used on this trade date", use get_latest_value_as_of()
    instead -- it doesn't require the caller to already know which
    period_end is relevant."""
    try:
        conn = _get_conn()
        row = conn.execute(
            """SELECT value, unit, form, period_end, filed_date, available_at
               FROM pit_observations
               WHERE source_key=? AND entity_key=? AND concept_key=? AND period_end=?
                 AND available_at <= ?
               ORDER BY available_at DESC LIMIT 1""",
            (source_key, entity_key, concept_key, period_end, as_of_date),
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.info("point_in_time_store: get_value_as_of failed for %s/%s/%s: %s",
                    source_key, entity_key, concept_key, e)
        return None


def get_latest_value_as_of(source_key: str, entity_key: str, concept_key: str,
                            as_of_date: str) -> Optional[dict]:
    """THE anti-look-ahead query: as of as_of_date, what's the most
    recently-available value for this concept, regardless of which
    period it covers -- picks the vintage with the latest period_end
    among all vintages whose available_at <= as_of_date. Returns None
    if nothing was knowable yet by that date (never falls back to a
    later value -- that would defeat the whole point)."""
    try:
        conn = _get_conn()
        row = conn.execute(
            """SELECT value, unit, form, period_end, filed_date, available_at
               FROM pit_observations
               WHERE source_key=? AND entity_key=? AND concept_key=?
                 AND available_at <= ?
               ORDER BY period_end DESC, available_at DESC LIMIT 1""",
            (source_key, entity_key, concept_key, as_of_date),
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.info("point_in_time_store: get_latest_value_as_of failed for %s/%s/%s: %s",
                    source_key, entity_key, concept_key, e)
        return None


def get_restatement_history(source_key: str, entity_key: str, concept_key: str,
                             period_end: str) -> List[dict]:
    """All vintages recorded for one exact period, oldest filed_date
    first -- lets a caller see "how many times was this period revised,
    and when did each revision become available"."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            """SELECT value, unit, form, filed_date, available_at
               FROM pit_observations
               WHERE source_key=? AND entity_key=? AND concept_key=? AND period_end=?
               ORDER BY filed_date ASC""",
            (source_key, entity_key, concept_key, period_end),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.info("point_in_time_store: get_restatement_history failed for %s/%s/%s: %s",
                    source_key, entity_key, concept_key, e)
        return []
