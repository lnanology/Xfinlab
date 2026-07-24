"""
Registration Risk Score Engine (2026-07-24 anti-abuse batch, layer 8 of
the registration architecture requested in chat: "AI風險分數").

Combines several already-free signals into ONE 0-100 risk score for a
registration attempt, instead of each check being an isolated pass/fail
gate as before. Modeled on the tiered scoring the user proposed
(<30 allow / 30-60 extra friction / 60-80 stricter verification / >80
reject), adapted to what this app actually has wired up:

  - Disposable email domain match (services/disposable_email_domains.py)
    stays an unconditional hard block BEFORE this ever runs -- that's not
    a "maybe" signal, so it's left as-is in backend/auth/auth.py.
  - CAPTCHA (services/captcha_service.py) is already a mandatory pass/
    fail gate for every registration -- it isn't a score input here
    either, since it never lets a failing attempt reach this code.
  - MX record missing (services/mx_check.py) -- NEW signal.
  - Device fingerprint reused by other recent registrations (this
    module's own device_fingerprints table) -- NEW signal.
  - Same IP registering repeatedly within the last hour -- reuses the
    EXISTING audit_logs table (action="register", written by
    services/audit_log_service.py's log_action()) rather than a new
    table, since that data is already being recorded on every signup.

Deliberately excluded: VPN/residential-proxy/Tor reputation. Reliable
versions of that check (IPQualityScore, AbuseIPDB, etc.) are paid
services -- see the 2026-07-24 chat audit this was scoped from, which
flagged that layer specifically as "usually costs money" and out of
scope for this free-tier pass.

Score bands (see compute_registration_risk()):
  score <  FLAG_THRESHOLD (40)   -> "allow": normal registration
  FLAG_THRESHOLD <= score < REJECT_THRESHOLD (70)
                                  -> "flag": account is created, but
                                     backend/auth/auth.py's login() will
                                     require email_verified=1 before this
                                     particular account can log in (see
                                     that file's login() for the check)
  score >= REJECT_THRESHOLD (70)  -> "reject": registration blocked
                                     outright (403), same as the existing
                                     disposable-email/captcha gates

Every function here fails OPEN on internal errors (never raises, worst
case degrades to score=0/"allow") -- consistent with this codebase's
established anti-abuse convention (see audit_log_service.py's
count_recent_failed_logins() for the same fail-open reasoning: a broken
check must never itself become a way to block legitimate signups).
"""
import logging
import os
import sqlite3
from typing import Dict, Optional

from services.mx_check import has_mx_record

logger = logging.getLogger(__name__)

# Same "..","..","xfinlab.db" convention as backend/auth/auth.py -- this
# file lives at services/ (one level below repo root), so only one ".."
# is needed to reach the canonical, Litestream-backed xfinlab.db.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

FLAG_THRESHOLD = 40
REJECT_THRESHOLD = 70

DEVICE_FP_WINDOW_HOURS = 24
IP_REGISTER_WINDOW_MINUTES = 60


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_device_fingerprints_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS device_fingerprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL,
            email TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_device_fp_fingerprint ON device_fingerprints(fingerprint)")
    conn.commit()
    conn.close()


init_device_fingerprints_table()


def _recent_fingerprint_reuse_count(fingerprint: str) -> int:
    """How many OTHER registration attempts already used this exact
    fingerprint in the last DEVICE_FP_WINDOW_HOURS. Fails open (0) on any
    DB error."""
    if not fingerprint:
        return 0
    try:
        conn = _get_db()
        row = conn.execute(
            "SELECT COUNT(*) as c FROM device_fingerprints "
            "WHERE fingerprint = ? AND created_at >= datetime('now', ?)",
            (fingerprint, f"-{DEVICE_FP_WINDOW_HOURS} hours"),
        ).fetchone()
        conn.close()
        return row["c"] if row else 0
    except Exception as e:
        logger.warning("fingerprint reuse count failed: %s", e)
        return 0


def _recent_ip_register_count(ip: str) -> int:
    """Reuses the EXISTING audit_logs table (action='register') -- no new
    table needed for this signal, since log_action() already writes an
    audit_logs row on every registration in backend/auth/auth.py. Fails
    open (0) on any DB error."""
    if not ip or ip == "unknown":
        return 0
    try:
        conn = _get_db()
        row = conn.execute(
            "SELECT COUNT(*) as c FROM audit_logs "
            "WHERE action = 'register' AND ip_address = ? AND created_at >= datetime('now', ?)",
            (ip, f"-{IP_REGISTER_WINDOW_MINUTES} minutes"),
        ).fetchone()
        conn.close()
        return row["c"] if row else 0
    except Exception as e:
        logger.warning("ip register count failed: %s", e)
        return 0


def record_device_fingerprint(fingerprint: Optional[str], email: str) -> None:
    """Called AFTER a registration succeeds, so this account's
    fingerprint counts toward the reuse score of any FUTURE registration
    attempt. Never raises -- a failed write here should never take down
    the registration response that already succeeded."""
    if not fingerprint:
        return
    try:
        conn = _get_db()
        conn.execute(
            "INSERT INTO device_fingerprints (fingerprint, email, created_at) VALUES (?, ?, datetime('now'))",
            (fingerprint, email),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("record_device_fingerprint failed: %s", e)


def compute_registration_risk(email: str, ip: str, fingerprint: Optional[str]) -> Dict:
    """Returns {"score": int 0-100, "reasons": [str, ...], "action":
    "allow"|"flag"|"reject"}. Never raises -- any internal failure
    degrades to score=0/"allow" (fail open), same convention as every
    other anti-abuse check in this codebase."""
    try:
        score = 0
        reasons = []

        try:
            if not has_mx_record(email):
                score += 50
                reasons.append("email_domain_no_mx")
        except Exception as e:
            logger.warning("MX check raised unexpectedly: %s", e)

        fp_reuse = _recent_fingerprint_reuse_count(fingerprint)
        if fp_reuse >= 3:
            score += 30
            reasons.append(f"device_fingerprint_reused_{fp_reuse}x")
        elif fp_reuse >= 1:
            score += 15
            reasons.append(f"device_fingerprint_reused_{fp_reuse}x")

        ip_count = _recent_ip_register_count(ip)
        if ip_count >= 5:
            score += 30
            reasons.append(f"ip_registered_{ip_count}x_last_hour")
        elif ip_count >= 3:
            score += 15
            reasons.append(f"ip_registered_{ip_count}x_last_hour")

        score = min(score, 100)
        if score >= REJECT_THRESHOLD:
            action = "reject"
        elif score >= FLAG_THRESHOLD:
            action = "flag"
        else:
            action = "allow"

        return {"score": score, "reasons": reasons, "action": action}
    except Exception as e:
        logger.warning("compute_registration_risk failed unexpectedly, failing open: %s", e)
        return {"score": 0, "reasons": ["risk_engine_error_failed_open"], "action": "allow"}
