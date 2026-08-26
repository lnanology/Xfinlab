"""2026-08-26 (AJ's "Data Factory" batch): self-registering registry for
every external data collector the site will ever have (FRED, ECB, SEC
EDGAR ownership, CFTC COT, crypto exchanges, GDELT, etc.).

Why this exists (the actual gap, confirmed by reading every existing
"collector"-shaped service before writing this): fred_macro_service.py /
ecb_macro_service.py / rss_news_service.py / capital_flow_engine.py all
hit real free APIs but only cache in-memory with a TTL -- nothing
persists, and there was no single place listing "what sources exist,
which are on, when did each last run, did it succeed". AJ explicitly
asked for auto-extensibility ("如有數據源自動展開") and an admin on/off +
notification mechanism ("可後台開關及通知") for a growing set of sources.

This deliberately does NOT reuse api/admin.py's existing feature_flags
table -- that table requires every key to be pre-listed in a hardcoded
_DEFAULT_FLAGS dict in code (set_feature_flag 404s otherwise), which is
the opposite of "a new collector shows up in admin automatically". Here,
register_source() is called once at import time by each collector module
itself (see the pattern note at the bottom of this file) -- writing the
collector file IS registering it; no second place to remember to update.
Same admin-panel on/off + fail-open-to-enabled posture as feature_flags,
just self-registering instead of hardcoded.

Kept in SQLite (same xfinlab.db every other service uses) -- NOT
PostgreSQL. Confirmed by auditing requirements.txt (no psycopg2/asyncpg)
and every other services/*.py file: raw sqlite3 against xfinlab.db is the
real, live pattern here, regardless of what any outside document assumed.
No new infra (no Postgres, no graph DB) until actual data volume justifies
it -- xfinlab.db is currently ~320KB, i.e. pre-scale.
"""
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

# Notification dedup: don't email AJ every single failed run of a flaky
# free API (some of these, e.g. GDELT/RSS, fail transiently and often) --
# only once per source per this window, mirroring the same
# should_send_upgrade_nudge()-style dedup used elsewhere in this codebase
# (services/intelligence_quota_service.py).
_FAILURE_NOTIFY_COOLDOWN_HOURS = 6


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data_sources (
            source_key TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            category TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            run_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            last_run_at TEXT,
            last_success_at TEXT,
            last_error TEXT,
            last_error_at TEXT,
            last_error_notified_at TEXT,
            registered_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def register_source(source_key: str, label: str, category: str, default_enabled: bool = True):
    """Idempotent -- safe to call every time the collector module is
    imported (i.e. every process start). Only ever INSERTs on first sight
    of a source_key; a re-registration never resets enabled/run stats for
    a source an admin has already toggled or that has run history, so
    redeploying never silently re-enables something an admin turned off.
    This single call is the entire "registration" step -- nothing else
    needs to be told a new collector exists."""
    conn = _get_db()
    conn.execute(
        """
        INSERT INTO data_sources (source_key, label, category, enabled)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(source_key) DO NOTHING
        """,
        (source_key, label, category, 1 if default_enabled else 0),
    )
    conn.commit()
    conn.close()


def is_source_enabled(source_key: str, default: bool = True) -> bool:
    """Fail-open (same posture as market_pulse.py's _feature_flag_enabled)
    -- a missing row/table/DB error must never be the reason a collector
    silently stops running. Callers should check this before doing any
    real work in a scheduled collector job."""
    try:
        conn = _get_db()
        row = conn.execute(
            "SELECT enabled FROM data_sources WHERE source_key=?", (source_key,)
        ).fetchone()
        conn.close()
        if row is None:
            return default
        return bool(row["enabled"])
    except Exception:
        return default


def set_source_enabled(source_key: str, enabled: bool) -> bool:
    """Admin toggle write (see api/admin.py's /admin/data-sources/{key}/
    toggle). Returns False if source_key isn't registered yet (nothing to
    toggle -- unlike feature_flags, this is a real "not found" since
    self-registration means every real collector already has a row)."""
    conn = _get_db()
    cur = conn.execute(
        "UPDATE data_sources SET enabled=? WHERE source_key=?",
        (1 if enabled else 0, source_key),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def record_run_start(source_key: str):
    conn = _get_db()
    conn.execute(
        "UPDATE data_sources SET run_count = run_count + 1, last_run_at = datetime('now') WHERE source_key=?",
        (source_key,),
    )
    conn.commit()
    conn.close()


def record_run_success(source_key: str):
    conn = _get_db()
    conn.execute(
        "UPDATE data_sources SET last_success_at = datetime('now'), last_error = NULL WHERE source_key=?",
        (source_key,),
    )
    conn.commit()
    conn.close()


def record_run_error(source_key: str, error_message: str):
    """Best-effort notification to AJ (services/email_service.py, same
    mailbox already used for every other operational email in this
    codebase) -- deduped to at most once per _FAILURE_NOTIFY_COOLDOWN_HOURS
    per source so a persistently-flaky free API doesn't spam his inbox.
    A notification failure never raises -- recording the error itself
    always succeeds regardless."""
    conn = _get_db()
    row = conn.execute(
        "SELECT last_error_notified_at, label FROM data_sources WHERE source_key=?", (source_key,)
    ).fetchone()
    conn.execute(
        """
        UPDATE data_sources
        SET error_count = error_count + 1, last_error = ?, last_error_at = datetime('now')
        WHERE source_key=?
        """,
        (error_message[:500], source_key),
    )
    conn.commit()

    should_notify = True
    if row and row["last_error_notified_at"]:
        try:
            last_notified = datetime.strptime(row["last_error_notified_at"], "%Y-%m-%d %H:%M:%S")
            should_notify = datetime.utcnow() - last_notified > timedelta(hours=_FAILURE_NOTIFY_COOLDOWN_HOURS)
        except (ValueError, TypeError):
            should_notify = True

    if should_notify:
        try:
            from services.email_service import EmailService
            from api.admin import ADMIN_EMAIL
            label = (row["label"] if row else source_key)
            html = f"""
            <div style="font-family:Arial,sans-serif;padding:20px;background:#080c14;color:#e2e8f0">
                <h2 style="color:#ef4444">Data source failing: {label}</h2>
                <p>Source key: <code>{source_key}</code></p>
                <p style="font-family:monospace;background:#111827;padding:12px;border-radius:8px;white-space:pre-wrap">{error_message[:500]}</p>
                <p style="color:#64748b;font-size:0.8rem">You won't get another one of these for this source for {_FAILURE_NOTIFY_COOLDOWN_HOURS}h. Toggle it off from the admin panel's Data Factory page if it needs to stay off longer.</p>
            </div>
            """
            sent = EmailService.send(ADMIN_EMAIL, f"[XFINLAB] Data source failing: {label}", html)
            if sent:
                conn.execute(
                    "UPDATE data_sources SET last_error_notified_at = datetime('now') WHERE source_key=?",
                    (source_key,),
                )
                conn.commit()
        except Exception:
            pass
    conn.close()


def list_sources() -> list:
    """For the admin panel's Data Factory page -- every registered
    source, regardless of enabled state, ordered by category then label
    so related collectors group together on screen."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM data_sources ORDER BY category, label"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Pattern every future collector module should follow (see services/
# fred_macro_service.py's planned migration for the first real example):
#
#   from services.data_source_registry import (
#       register_source, is_source_enabled, record_run_start,
#       record_run_success, record_run_error,
#   )
#   register_source("fred_macro", "FRED Macro Data", "macro")
#
#   def fetch_and_store():
#       if not is_source_enabled("fred_macro"):
#           return
#       record_run_start("fred_macro")
#       try:
#           ...real fetch + persist...
#           record_run_success("fred_macro")
#       except Exception as e:
#           record_run_error("fred_macro", str(e))
#
# That's the entire integration surface -- no separate registration step,
# no admin.html edit, no new endpoint. The admin Data Factory page reads
# list_sources() and will show this the moment the module is imported.
# ---------------------------------------------------------------------------
