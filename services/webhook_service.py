"""
Intelligence API Webhooks -- 2026-08-28 (AJ: "重有咩賺錢位" -> picked
"Webhook (Pro專屬)" as one of 3 next monetization moves).

Why this is Pro-only and why it's a real differentiator: every endpoint
in api/intelligence.py today is pull/polling-only -- a developer has to
keep hitting an endpoint to notice a new insider filing or a VIX regime
flip. Competing congressional-trading/alt-data APIs (e.g. congressinvests.
com, researched during the earlier Data Factory sourcing pass) sell
webhook push notifications specifically as their Pro-tier differentiator.
This mirrors that shape using XFINLAB's own real Data Factory events
instead of a third-party indie API.

Scope, deliberately narrow for a first version -- only 2 event types,
both hooked into scheduled jobs that ALREADY run daily (no new polling
infrastructure needed):
  - "vix_regime_change": market-wide (no ticker), fires when services/
    cboe_vix_service.py's contango/backwardation read flips from the
    previously observed state. Backed by backend/main.py's existing
    cboe_vix_refresh job.
  - "new_13d_filing": per-ticker, fires when services/
    sec_13d_13g_service.py's refresh_all() sees a ticker's filing COUNT
    increase since the last run. Backed by that module's existing daily
    scheduled job.

Both are genuinely event-driven (not "check every N minutes and hope"),
so this can honestly promise "same-day" delivery, gated by the
underlying collector's own refresh cadence -- never a fabricated
"real-time" claim this codebase can't back up.

Delivery is fire-and-forget from inside the scheduled job (best-effort,
short timeout, single attempt -- a slow/dead third-party receiver must
never stall XFINLAB's own scheduler). A subscription that fails
_MAX_CONSECUTIVE_FAILURES deliveries in a row is auto-deactivated
(never silently retried forever against a URL that's clearly gone) --
same "record but never sabotage the rest of the system" posture as
services/data_source_registry.py's record_run_error.
"""
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

VALID_EVENT_TYPES = {
    "vix_regime_change": {"per_ticker": False, "label": "VIX contango/backwardation regime change"},
    "new_13d_filing": {"per_ticker": True, "label": "New 13D activist filing for a watched ticker"},
    # 2026-08-31 (AJ: "加Webhook提醒" -- Opportunity Radar follow-up):
    # market-wide, no ticker (Opportunity Radar itself has no ticker
    # concept). See check_and_deliver_opportunity_radar_shift() below.
    "opportunity_radar_shift": {"per_ticker": False, "label": "An Opportunity Radar industry's net improving/worsening lean flipped"},
}

_MAX_CONSECUTIVE_FAILURES = 5  # auto-deactivate after this many delivery failures in a row
_DELIVERY_TIMEOUT_SECONDS = 8  # short -- a slow receiver must never stall the scheduler job calling deliver()
WEBHOOK_USER_AGENT = "XFINLABBot-Webhooks/1.0 (+https://www.xfinlab.com; contact: support@xfinlab.com)"

_MAX_SUBSCRIPTIONS_PER_KEY = 20  # generous but bounded -- prevents one key from fanning out unbounded HTTP calls every job run


def _get_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS intelligence_webhooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT NOT NULL,
            event_type TEXT NOT NULL,
            ticker TEXT,
            url TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            fail_count INTEGER NOT NULL DEFAULT 0,
            last_delivered_at TEXT,
            last_status_code INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_webhooks_event_ticker ON intelligence_webhooks(event_type, ticker, active)")
    # Tiny generic key->value state store, scoped to this module -- lets
    # the two check_and_deliver_* functions below remember "what did we
    # see last time" (last VIX structure, last 13D filing count per
    # ticker) without needing a shared KV table (this codebase doesn't
    # have one) or pushing scheduler-job state into cboe_vix_service.py/
    # sec_13d_13g_service.py, which have no reason to know webhooks exist.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhook_event_state (
            state_key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def _get_state(state_key: str) -> Optional[str]:
    conn = _get_db()
    row = conn.execute("SELECT value FROM webhook_event_state WHERE state_key=?", (state_key,)).fetchone()
    conn.close()
    return row["value"] if row else None


def _set_state(state_key: str, value: str):
    conn = _get_db()
    conn.execute(
        """
        INSERT INTO webhook_event_state (state_key, value, updated_at) VALUES (?, ?, datetime('now'))
        ON CONFLICT(state_key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (state_key, value),
    )
    conn.commit()
    conn.close()


def subscribe(api_key: str, event_type: str, url: str, ticker: Optional[str] = None) -> Dict:
    """Returns {"ok": True, "id": ...} or {"ok": False, "error": "..."}.
    Validates event_type against VALID_EVENT_TYPES, requires https:// (no
    plain http webhook targets -- matches Stripe/most providers' own
    production webhook requirement), requires a ticker for per-ticker
    event types and rejects one for market-wide types (a ticker on
    vix_regime_change would silently never fire -- fail loud instead)."""
    meta = VALID_EVENT_TYPES.get(event_type)
    if not meta:
        return {"ok": False, "error": f"Unknown event_type {event_type!r}. Valid: {sorted(VALID_EVENT_TYPES)}"}

    url = (url or "").strip()
    if not url.startswith("https://"):
        return {"ok": False, "error": "url must start with https://"}

    ticker = (ticker or "").upper().strip() or None
    if meta["per_ticker"] and not ticker:
        return {"ok": False, "error": f"event_type {event_type!r} requires a ticker"}
    if not meta["per_ticker"] and ticker:
        return {"ok": False, "error": f"event_type {event_type!r} is market-wide -- do not pass a ticker"}

    conn = _get_db()
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM intelligence_webhooks WHERE api_key=? AND active=1", (api_key,)
    ).fetchone()["n"]
    if count >= _MAX_SUBSCRIPTIONS_PER_KEY:
        conn.close()
        return {"ok": False, "error": f"Max {_MAX_SUBSCRIPTIONS_PER_KEY} active webhook subscriptions per key"}

    cur = conn.execute(
        "INSERT INTO intelligence_webhooks (api_key, event_type, ticker, url) VALUES (?, ?, ?, ?)",
        (api_key, event_type, ticker, url),
    )
    conn.commit()
    webhook_id = cur.lastrowid
    conn.close()
    return {"ok": True, "id": webhook_id}


def unsubscribe(api_key: str, webhook_id: int) -> bool:
    """True only if a row matching BOTH webhook_id and api_key was
    deleted -- a caller can never unsubscribe another key's webhook by
    guessing an id."""
    conn = _get_db()
    cur = conn.execute(
        "DELETE FROM intelligence_webhooks WHERE id=? AND api_key=?", (webhook_id, api_key)
    )
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def list_for_key(api_key: str) -> List[dict]:
    conn = _get_db()
    rows = conn.execute(
        "SELECT id, event_type, ticker, url, active, fail_count, last_delivered_at, last_status_code, created_at "
        "FROM intelligence_webhooks WHERE api_key=? ORDER BY created_at DESC",
        (api_key,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deliver(event_type: str, payload: dict, ticker: Optional[str] = None) -> Dict[str, int]:
    """Called from a scheduled job when a real event has actually
    happened (never speculatively). Looks up every active subscription
    matching (event_type, ticker) -- ticker=None matches market-wide
    subscriptions (which were themselves stored with ticker=NULL).
    POSTs {"event": event_type, "ticker": ticker, "data": payload,
    "delivered_at": ...} to each. Best-effort: an exception delivering to
    one URL never stops delivery to the others, and never propagates up
    to break the caller's scheduled job. Returns {"attempted": n, "ok": n}
    for the job's own logging."""
    ticker = (ticker or "").upper().strip() or None
    conn = _get_db()
    rows = conn.execute(
        "SELECT id, url, fail_count FROM intelligence_webhooks WHERE event_type=? AND ticker IS ? AND active=1",
        (event_type, ticker),
    ).fetchall()
    conn.close()

    if not rows:
        return {"attempted": 0, "ok": 0}

    body = {
        "event": event_type,
        "ticker": ticker,
        "data": payload,
        "delivered_at": datetime.now(timezone.utc).isoformat(),
    }

    attempted = 0
    ok = 0
    conn = _get_db()
    for row in rows:
        attempted += 1
        status_code = None
        try:
            res = requests.post(
                row["url"],
                json=body,
                headers={"User-Agent": WEBHOOK_USER_AGENT},
                timeout=_DELIVERY_TIMEOUT_SECONDS,
            )
            status_code = res.status_code
            success = 200 <= res.status_code < 300
        except Exception as e:
            logger.info("webhook_service: delivery to webhook id=%s failed: %s", row["id"], e)
            success = False

        if success:
            conn.execute(
                "UPDATE intelligence_webhooks SET fail_count=0, last_delivered_at=datetime('now'), last_status_code=? WHERE id=?",
                (status_code, row["id"]),
            )
            ok += 1
        else:
            new_fail_count = row["fail_count"] + 1
            deactivate = new_fail_count >= _MAX_CONSECUTIVE_FAILURES
            conn.execute(
                "UPDATE intelligence_webhooks SET fail_count=?, last_delivered_at=datetime('now'), last_status_code=?, active=? WHERE id=?",
                (new_fail_count, status_code, 0 if deactivate else 1, row["id"]),
            )
            if deactivate:
                logger.info("webhook_service: webhook id=%s auto-deactivated after %s consecutive failures", row["id"], new_fail_count)
    conn.commit()
    conn.close()
    return {"attempted": attempted, "ok": ok}


def check_and_deliver_vix_regime_change(current_structure: Optional[str]) -> Optional[Dict]:
    """Call this from backend/main.py's cboe_vix_refresh job right after
    services/cboe_vix_service.get_snapshot() -- pass its "structure"
    field (contango/backwardation/flat/None). Fires vix_regime_change
    webhooks ONLY on an actual observed change from the previously
    recorded structure -- the very first time this ever runs (no prior
    state) just records the baseline and does NOT fire, since "first
    observation" isn't a change. Returns the deliver() result dict, or
    None if nothing fired this run."""
    if not current_structure:
        return None
    previous = _get_state("vix_structure")
    _set_state("vix_structure", current_structure)
    if previous is None or previous == current_structure:
        return None
    result = deliver(
        "vix_regime_change",
        {"previous_structure": previous, "new_structure": current_structure},
    )
    logger.info("webhook_service: vix_regime_change %s -> %s, delivered to %s/%s webhooks",
                previous, current_structure, result["ok"], result["attempted"])
    return result


def check_and_deliver_new_13d_filings(ticker_filing_counts: Dict[str, int]) -> Dict[str, Dict]:
    """Call this from backend/main.py's sec_13d_13g_refresh job with the
    exact {ticker: filing_count} dict services/sec_13d_13g_service.
    refresh_all() already returns. Fires new_13d_filing for any ticker
    whose count increased since the last run (a negative-sentinel -1
    from that module's own per-ticker error handling is treated as "no
    change", never a fabricated decrease/increase). First-ever
    observation per ticker records the baseline without firing, same
    no-spurious-first-fire rule as the VIX check above. Returns
    {ticker: deliver_result} for every ticker that actually fired."""
    fired = {}
    for ticker, count in ticker_filing_counts.items():
        if count is None or count < 0:
            continue  # -1 sentinel = this ticker's fetch failed this run, not a real "0 filings"
        state_key = f"13d_count:{ticker}"
        previous_raw = _get_state(state_key)
        _set_state(state_key, str(count))
        if previous_raw is None:
            continue  # baseline only, first time seeing this ticker
        try:
            previous = int(previous_raw)
        except ValueError:
            continue
        if count > previous:
            result = deliver(
                "new_13d_filing",
                {"previous_count": previous, "new_count": count},
                ticker=ticker,
            )
            fired[ticker] = result
    if fired:
        logger.info("webhook_service: new_13d_filing fired for tickers: %s", sorted(fired))
    return fired


def check_and_deliver_opportunity_radar_shift(industries: Dict[str, Dict]) -> Dict[str, Dict]:
    """Call this from backend/main.py's opportunity_radar_shift_check job
    with the exact `industries` dict services.opportunity_radar_service.
    get_opportunity_radar() returns. This function does not fetch
    anything itself -- it only re-derives each industry's NET LEAN from
    the already-computed improving_count/worsening_count and diffs it
    against the last observed lean.

    Net lean per industry: "improving" if improving_count > worsening_count,
    "worsening" if worsening_count > improving_count, "mixed" otherwise
    (a tie -- including 0-0 when that industry's own data source key
    isn't configured, since a source-less industry has zero real
    indicators and must never be assigned a fabricated lean).

    Fires opportunity_radar_shift ONLY when an industry's lean flips
    between the two non-mixed states (improving<->worsening). A flip
    into or out of "mixed" is deliberately NOT fire-worthy on its own --
    a single indicator wobbling across the flat threshold could nudge a
    3-improving/3-worsening industry into "mixed" without the industry
    genuinely reversing course, and firing on that would be noise, not
    signal. First-ever observation per industry records the baseline
    without firing, same no-spurious-first-fire rule as the other 2
    event types above. Returns {industry_key: deliver_result} for every
    industry that actually fired this run."""
    fired = {}
    for industry_key, data in (industries or {}).items():
        improving = data.get("improving_count", 0) or 0
        worsening = data.get("worsening_count", 0) or 0
        if improving > worsening:
            lean = "improving"
        elif worsening > improving:
            lean = "worsening"
        else:
            lean = "mixed"

        state_key = f"opportunity_radar_lean:{industry_key}"
        previous = _get_state(state_key)
        _set_state(state_key, lean)

        if previous is None or previous == lean:
            continue  # baseline-only, or genuinely unchanged
        if "mixed" in (previous, lean):
            continue  # flip into/out of mixed alone isn't fire-worthy, see docstring

        result = deliver(
            "opportunity_radar_shift",
            {
                "industry": industry_key,
                "previous_lean": previous,
                "new_lean": lean,
                "improving_count": improving,
                "worsening_count": worsening,
                "summary": data.get("summary"),
            },
        )
        fired[industry_key] = result
    if fired:
        logger.info("webhook_service: opportunity_radar_shift fired for industries: %s", sorted(fired))
    return fired
