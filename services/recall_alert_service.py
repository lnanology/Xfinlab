"""
Recall Alert -- no-code email subscriptions -- 2026-09-14/15 (AJ:
combination-strategy follow-up to the API+webhook Recall Alert product
built earlier the same day: "係，改做no-code email表單做主產品（推薦）").

Why this exists as its own module rather than living inside
webhook_service.py: the intended customer for THIS layer is explicitly
NOT the developer audience webhook_service.py's recall_match event type
was built for -- a small Amazon/Shopify/food/supplement seller almost
certainly isn't a programmer and will never get an API key or wire up a
webhook receiver. This module lets that person subscribe with nothing
but an email address and a brand/product keyword (same public,
no-API-key-required shape as api/feedback.py), and get a plain email
when a new CPSC or FDA recall matches.

Deliberately reuses, rather than duplicates:
  - services/webhook_service.py's get_state()/set_state() KV table for
    "what recall_ids have we already seen for this keyword" -- promoted
    to public this same day specifically so this module could share it.
    One diff per keyword per scheduler run (see backend/main.py's
    _run_recall_alert_scan_job), fanned out to BOTH webhook subscribers
    (services.webhook_service.check_and_deliver_recall_matches) and the
    email subscribers this module tracks -- never two independent diffs
    against the same state_key in the same run (the second would always
    see zero new items, since the first already advanced the baseline).
  - services/cpsc_service.py's search_recalls_by_keyword() and services/
    openfda_service.py's search_food_drug_device_recalls_by_keyword() --
    merged into one combined "recall_id"-keyed list per keyword (see
    get_merged_recalls_for_keyword() below), so one email subscription
    covers general consumer products (CPSC) AND food/drug/device (FDA)
    with a single keyword, matching the "combination strategy" AJ asked
    for after option-2/3 niche research came up empty (bank health/fuel/
    13D/COT/FINRA short interest/Form4 all already had Apify-scraper
    competitors -- see chat).
  - services/email_service.py's EmailService.send() for delivery -- no
    new email infra, just a new template (send_recall_alert()).

Every subscription gets its own random unsubscribe token (NOT derived
from email+keyword) so an unsubscribe link never leaks a guessable
pattern and works even if the same email subscribes to the same keyword
twice (each row/token independent, deactivating one never silently
deactivates a different subscription for the same address).
"""
import logging
import os
import secrets
import sqlite3
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

_MAX_SUBSCRIPTIONS_PER_EMAIL = 10  # generous but bounded, same posture as webhook_service.py's per-key cap


def _get_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recall_email_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            keyword TEXT NOT NULL,
            unsubscribe_token TEXT UNIQUE NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recall_email_keyword ON recall_email_subscriptions(keyword, active)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recall_email_token ON recall_email_subscriptions(unsubscribe_token)")
    conn.commit()
    conn.close()


_init_table()


def _valid_email(email: str) -> bool:
    """Deliberately minimal -- same "don't over-engineer validation"
    posture as api/feedback.py's public form. Real deliverability is
    proven by the send itself, not a regex."""
    email = (email or "").strip()
    return bool(email) and "@" in email and "." in email.split("@")[-1] and len(email) <= 254


def subscribe(email: str, keyword: str) -> Dict:
    """Returns {"ok": True, "id": ...} or {"ok": False, "error": "..."}
    -- never raises, mirrors api/feedback.py's tolerant public-form
    posture. A duplicate (same email, same keyword, still active) is
    treated as already-subscribed rather than creating a second row."""
    email = (email or "").strip().lower()
    # Uppercased for the same reason webhook_service.subscribe() uppercases
    # its `ticker` column (which, for recall_match, also holds a free-text
    # keyword, not a real ticker) -- keeps both channels' stored casing
    # consistent so backend/main.py's scheduled job can match a single
    # canonical keyword against both webhook and email subscribers without
    # a case-insensitive query on either side.
    keyword = (keyword or "").strip().upper()
    if not _valid_email(email):
        return {"ok": False, "error": "invalid_email"}
    if not keyword:
        return {"ok": False, "error": "invalid_keyword"}

    conn = _get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM recall_email_subscriptions WHERE email=? AND keyword=? AND active=1",
            (email, keyword),
        ).fetchone()
        if existing:
            return {"ok": True, "id": existing["id"], "already_subscribed": True}

        count = conn.execute(
            "SELECT COUNT(*) AS n FROM recall_email_subscriptions WHERE email=? AND active=1",
            (email,),
        ).fetchone()["n"]
        if count >= _MAX_SUBSCRIPTIONS_PER_EMAIL:
            return {"ok": False, "error": "too_many_subscriptions"}

        token = secrets.token_urlsafe(24)
        cur = conn.execute(
            "INSERT INTO recall_email_subscriptions (email, keyword, unsubscribe_token) VALUES (?, ?, ?)",
            (email, keyword, token),
        )
        conn.commit()
        return {"ok": True, "id": cur.lastrowid, "unsubscribe_token": token}
    finally:
        conn.close()


def unsubscribe(token: str) -> bool:
    """True if a real active subscription was deactivated, False for an
    unknown/already-inactive token -- never raises."""
    if not token:
        return False
    conn = _get_db()
    try:
        cur = conn.execute(
            "UPDATE recall_email_subscriptions SET active=0 WHERE unsubscribe_token=? AND active=1",
            (token,),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_active_keywords() -> List[str]:
    """Every distinct keyword with at least one active email
    subscription -- case-preserving as stored (matches webhook_service.
    list_active_tickers_for_event's "ticker" column convention, which
    for recall_match already holds free-text keywords, not tickers)."""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT keyword FROM recall_email_subscriptions WHERE active=1"
        ).fetchall()
        return [r["keyword"] for r in rows]
    finally:
        conn.close()


def list_active_subscriptions_for_keyword(keyword: str) -> List[Dict]:
    """{"email", "unsubscribe_token"} rows for every active subscriber
    watching this exact keyword -- used by backend/main.py's scheduled
    job to fan out one email per subscriber per new-recall batch."""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT email, unsubscribe_token FROM recall_email_subscriptions WHERE keyword=? AND active=1",
            (keyword,),
        ).fetchall()
        return [{"email": r["email"], "unsubscribe_token": r["unsubscribe_token"]} for r in rows]
    finally:
        conn.close()


def get_merged_recalls_for_keyword(keyword: str, limit: int = 10) -> Dict:
    """Combines cpsc_service.search_recalls_by_keyword() (general
    consumer products) and openfda_service.search_food_drug_device_
    recalls_by_keyword() (food/drug/device) into one "recall_id"-keyed
    list for a single keyword -- the "combination strategy" product:
    one subscription, both agencies. `fetch_error` is True only if BOTH
    sources failed outright this call (a real, if partial, result from
    even one source is worth surfacing rather than discarding)."""
    from services.cpsc_service import search_recalls_by_keyword
    from services.openfda_service import search_food_drug_device_recalls_by_keyword

    cpsc_result = search_recalls_by_keyword(keyword, limit=limit)
    fda_result = search_food_drug_device_recalls_by_keyword(keyword, limit=limit)

    merged = list(cpsc_result.get("recent") or []) + list(fda_result.get("recent") or [])
    merged.sort(key=lambda r: r.get("date") or "", reverse=True)
    merged = merged[:limit]

    both_failed = bool(cpsc_result.get("fetch_error")) and bool(fda_result.get("fetch_error"))
    return {
        "keyword": keyword,
        "count": len(merged),
        "recent": merged,
        "fetch_error": both_failed,
    }
