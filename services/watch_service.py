"""
"What Changed?" entity monitoring -- 2026-10-01 (AJ: "找出未做的賺錢路線,
開發更新穎賺錢機會" follow-up #2, after Research Memory/Hypothesis API).
Every per-ticker endpoint in api/intelligence.py today answers "what IS
true right now" -- a developer has to keep polling and diff the responses
themselves to notice anything changed. This closes that gap the same way
webhook_service.py's existing event types already do (vix_regime_change,
new_13d_filing, opportunity_radar_shift, recall_match): a daily scheduled
job computes a fresh snapshot, diffs it against yesterday's, and fires a
webhook ONLY when something real moved.

Deliberately reuses 100% of existing infrastructure rather than building
a parallel subscription system:
  - Registers as a new event_type ("watch_digest") in webhook_service.
    VALID_EVENT_TYPES, so POST /v1/webhooks/subscribe, GET /v1/webhooks,
    and DELETE /v1/webhooks/{id} all already work for it with zero new
    API endpoints -- a developer subscribes with
    {"event_type": "watch_digest", "ticker": "NVDA", "url": "https://..."}
    exactly like they would for new_13d_filing.
  - Reuses webhook_service.get_state()/set_state() for the snapshot diff
    (same KV table new_13d_filing's per-ticker counter already uses) and
    webhook_service.deliver() for the actual HTTP push (same retry/auto-
    deactivate/best-effort posture every other event type gets).
  - Reuses webhook_service.list_active_tickers_for_event() so the daily
    job only computes snapshots for tickers someone is actually watching,
    never a fixed universe.

compute_snapshot() deliberately sources every field from services already
live elsewhere in this API (technical_analysis_service, sec_form4_service,
finra_short_interest_service, rss_news_service) -- no new data source, no
new network call shape, same honesty posture as every other endpoint in
this product: a field that can't be computed for a given ticker is simply
omitted from the snapshot (and therefore never diffed), not fabricated as
"no change".
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

EVENT_TYPE = "watch_digest"

# Fields worth alerting on if they change meaningfully -- deliberately a
# short, high-signal list rather than every field technical_analysis_
# service returns (a 0.1-point confidence wobble on every run would make
# this noisy/useless; see _has_meaningful_change()'s per-field thresholds).
_TRACKED_FIELDS = (
    "confluence_direction",
    "price",
    "headline_count_7d",
    "insider_tx_count_30d",
    "short_interest_shares",
)


def compute_snapshot(ticker: str) -> Dict:
    """Best-effort -- any individual source failing just omits that field
    rather than failing the whole snapshot (same posture as /v1/impact
    and /v1/company-network's sub-field degradation)."""
    ticker = ticker.upper().strip()
    snapshot: Dict = {}

    try:
        from services.technical_analysis_service import get_technical_analysis
        tech = get_technical_analysis(ticker)
        if tech and "error" not in tech:
            snapshot["price"] = tech.get("last_close")
            confluence = tech.get("confluence") or {}
            snapshot["confluence_direction"] = confluence.get("direction")
            snapshot["confluence_confidence_pct"] = confluence.get("confidence_pct")
    except Exception as e:
        logger.info("watch_service: technical snapshot failed for %s: %s", ticker, e)

    try:
        from services.rss_news_service import search_headlines
        headlines = search_headlines(query=ticker, limit=50)
        if headlines.get("status") == "ok":
            snapshot["headline_count_7d"] = len(headlines.get("items") or [])
    except Exception as e:
        logger.info("watch_service: headline snapshot failed for %s: %s", ticker, e)

    try:
        from services.sec_form4_service import get_recent_insider_transactions
        insider = get_recent_insider_transactions(ticker)
        if insider and insider.get("available"):
            snapshot["insider_tx_count_30d"] = len(insider.get("transactions") or [])
    except Exception as e:
        logger.info("watch_service: insider snapshot failed for %s: %s", ticker, e)

    try:
        from services.finra_short_interest_service import get_short_interest_for_ticker
        short_interest = get_short_interest_for_ticker(ticker)
        if short_interest and short_interest.get("available"):
            snapshot["short_interest_shares"] = short_interest.get("current_short_shares")
    except Exception as e:
        logger.info("watch_service: short-interest snapshot failed for %s: %s", ticker, e)

    return snapshot


def _has_meaningful_change(field: str, previous, current) -> bool:
    """Per-field noise threshold -- a direction flip always counts, but a
    price/count field only counts if it moved more than a small tolerance,
    so a $0.01 price tick or a single stray headline doesn't trigger a
    webhook every single day."""
    if previous is None or current is None:
        return False
    if field == "confluence_direction":
        return previous != current
    if field == "price":
        try:
            if not previous:
                return False
            return abs((float(current) - float(previous)) / float(previous)) >= 0.02  # 2%+ move
        except (TypeError, ValueError, ZeroDivisionError):
            return False
    if field in ("headline_count_7d", "insider_tx_count_30d"):
        try:
            return int(current) != int(previous)
        except (TypeError, ValueError):
            return False
    if field == "short_interest_shares":
        try:
            if not previous:
                return False
            return abs((float(current) - float(previous)) / float(previous)) >= 0.05  # 5%+ move
        except (TypeError, ValueError, ZeroDivisionError):
            return False
    return previous != current


def check_and_deliver_watch_digest(ticker: str) -> Optional[Dict]:
    """Call once per watched ticker from backend/main.py's daily
    watch_digest_scan job. Computes a fresh snapshot, diffs against the
    previously stored one (webhook_service's generic state KV, keyed
    `watch_snapshot:{ticker}`), and fires the webhook ONLY if at least one
    tracked field changed meaningfully. First-ever observation for a
    ticker just records the baseline and does not fire -- same
    no-spurious-first-fire rule as every other check_and_deliver_* in
    webhook_service.py. Returns the deliver() result dict, or None if
    nothing fired this run (including: no active subscribers, first
    observation, or no meaningful change)."""
    import json as _json
    from services.webhook_service import get_state, set_state, deliver

    ticker = ticker.upper().strip()
    current = compute_snapshot(ticker)
    if not current:
        return None  # every source failed this run -- don't diff against a blank snapshot

    state_key = f"watch_snapshot:{ticker}"
    previous_raw = get_state(state_key)
    set_state(state_key, _json.dumps(current))

    if previous_raw is None:
        return None  # baseline only, first time watching this ticker

    try:
        previous = _json.loads(previous_raw)
    except (ValueError, TypeError):
        return None

    changes: List[Dict] = []
    for field in _TRACKED_FIELDS:
        prev_val = previous.get(field)
        cur_val = current.get(field)
        if field not in current:
            continue  # this run's snapshot couldn't compute this field -- don't diff a missing value
        if _has_meaningful_change(field, prev_val, cur_val):
            changes.append({"field": field, "previous": prev_val, "current": cur_val})

    if not changes:
        return None

    result = deliver(EVENT_TYPE, {"changes": changes, "snapshot": current}, ticker=ticker)
    logger.info("watch_service: watch_digest fired for %s (%d changes), delivered to %s/%s webhooks",
                ticker, len(changes), result["ok"], result["attempted"])
    return result
