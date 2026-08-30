"""
Company Network Phase 3: Event -> Price Reaction -- 2026-08-30
(per AJ: "起 Phase 2 3 一次過").

What this deliberately is NOT: a predicted/expected price impact, a
"historical average reaction" statistic, or any kind of confidence/
fragility score. engines/event_engine.py's own module docstring already
documents why: this exact codebase previously had (and explicitly
removed) a feature that claimed "similar historical events react by
X% on average" backed by database/event_history.sql -- a table whose
own comment admits it is hand-made "Sample Data", not real recorded
market history. Reviving that shape of feature, even with a new name,
would repeat the same fabricated-numbers mistake this session has
flagged and fixed multiple times elsewhere (feature_engine.py, stress-
lab.html, the old MasterPipeline modules).

What this IS instead: for each of a ticker's most recent REAL, dated
events already tracked by this Data Factory (a Form 4 insider
transaction, a 13D/13G activist filing), fetch REAL historical daily
closes (via services/technical_analysis_service.fetch_ohlc_history --
already Alpaca-first/yfinance-fallback, same routing every other price
chart in this app uses) and report what the price actually, factually
did afterward. One event, one real outcome, computed fresh at request
time -- never averaged across events, never presented as a prediction,
never implied to be caused by the event. Every response repeats this
distinction in `method_note` so it can never be quoted out of context
as a forecast.

If a ticker has no tracked Form 4 / 13D-13G events, or the event is too
recent for enough trading days to have elapsed, this honestly returns
`available: False` / partial `null` offsets rather than inventing
placeholder numbers.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

ATTRIBUTION = (
    "Price reactions computed at request time from real historical daily "
    "closes (Alpaca/yfinance) around actual SEC Form 4 / 13D-13G filing "
    "dates already collected by XFINLAB's Data Factory. Describes what "
    "happened after ONE specific past event -- not a prediction, not an "
    "average across events, and not a claim of causation."
)

_OFFSETS = (0, 1, 5, 10, 20)
_MAX_EVENTS = 3


def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    df.index = idx
    return df


def _price_reaction(df: pd.DataFrame, event_date_str: str) -> Optional[Dict]:
    """Returns the real close on/after `event_date_str` and at each of
    _OFFSETS trading days later, or None if the date isn't covered by
    `df` at all (e.g. event predates the fetched history window)."""
    if df is None or df.empty or not event_date_str:
        return None
    try:
        df = _normalize_index(df)
        event_ts = pd.Timestamp(event_date_str)
        # If the event predates the fetched history window entirely, don't
        # silently match it to the window's first bar -- that would report
        # a fabricated "reaction" starting on the wrong date. Only honest
        # if the event date actually falls within (or a few days before,
        # covering weekends/holidays) the fetched range.
        if event_ts < (df.index[0].normalize() - pd.Timedelta(days=5)):
            return None
        on_or_after = df.index[df.index.normalize() >= event_ts]
        if len(on_or_after) == 0:
            return None
        start_pos = df.index.get_loc(on_or_after[0])
        base_close = float(df.iloc[start_pos]["Close"])
        reaction = {
            "matched_trading_date": str(df.index[start_pos].date()),
            "close_on_matched_date": round(base_close, 4),
            "offsets": {},
        }
        for off in _OFFSETS:
            pos = start_pos + off
            key = "same_day" if off == 0 else f"{off}d_later"
            if pos < len(df):
                close = float(df.iloc[pos]["Close"])
                pct = round(((close - base_close) / base_close) * 100, 2) if base_close else None
                reaction["offsets"][key] = {
                    "date": str(df.index[pos].date()),
                    "close": round(close, 4),
                    "pct_change_from_event": pct,
                }
            else:
                reaction["offsets"][key] = None  # not enough trading history since the event yet
        return reaction
    except Exception as e:
        logger.info("event_impact_service: price reaction lookup failed: %s", e)
        return None


def get_event_impact(ticker: str) -> Dict:
    """Returns:
        {"available": True, "ticker": "AAPL", "attribution": "...",
         "events": [{"event_type": "insider_transaction"|"activist_filing",
                      "event_date": "...", "description": "...",
                      "price_reaction": {...} | None}, ...],
         "method_note": "..."}
        {"available": False, "message": "..."} if no dated events are
        currently tracked for this ticker.

    Always synchronous, read-only against already-collected Data Factory
    tables (via sec_form4_service / sec_13d_13g_service) plus one live
    OHLC fetch -- never writes anything itself."""
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return {"available": False, "message": "ticker is required"}

    from services.sec_form4_service import get_recent_insider_transactions
    from services.sec_13d_13g_service import search_recent_filings

    events: List[Dict] = []

    try:
        insider = get_recent_insider_transactions(ticker)
        if insider.get("available"):
            rows = insider.get("transactions") or []
            rows = sorted(rows, key=lambda r: r.get("transaction_date") or "", reverse=True)
            for t in rows[:_MAX_EVENTS]:
                if not t.get("transaction_date"):
                    continue
                code = t.get("transaction_code") or "?"
                action = {"P": "purchased", "S": "sold"}.get(code, f"reported a code-{code} transaction on")
                shares = t.get("shares")
                events.append({
                    "event_type": "insider_transaction",
                    "event_date": t["transaction_date"],
                    "description": (
                        f"Insider {t.get('insider_name') or 'unknown'} {action} "
                        f"{shares:,.0f} shares" if isinstance(shares, (int, float)) else
                        f"Insider {t.get('insider_name') or 'unknown'} {action} shares"
                    ),
                })
    except Exception as e:
        logger.info("event_impact_service: insider event lookup failed for %s: %s", ticker, e)

    try:
        activist = search_recent_filings(ticker)
        if activist.get("available"):
            filings = sorted(activist.get("filings") or [], key=lambda f: f.get("file_date") or "", reverse=True)
            for f in filings[:_MAX_EVENTS]:
                if not f.get("file_date"):
                    continue
                events.append({
                    "event_type": "activist_filing",
                    "event_date": f["file_date"],
                    "description": (
                        f"{f.get('filer_display_name') or 'An investor'} filed a "
                        f"{f.get('form_type') or 'Schedule 13D/13G'} disclosing a stake"
                    ),
                })
    except Exception as e:
        logger.info("event_impact_service: activist event lookup failed for %s: %s", ticker, e)

    if not events:
        return {
            "available": False,
            "message": f"No dated Form 4 or 13D/13G events currently tracked for {ticker}",
        }

    events.sort(key=lambda e: e["event_date"], reverse=True)
    events = events[:_MAX_EVENTS]

    df = None
    try:
        from services.technical_analysis_service import fetch_ohlc_history
        df = fetch_ohlc_history(ticker, period="1y", interval="1d")
    except Exception as e:
        logger.info("event_impact_service: OHLC fetch failed for %s: %s", ticker, e)

    for e in events:
        e["price_reaction"] = _price_reaction(df, e["event_date"])

    return {
        "available": True,
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "attribution": ATTRIBUTION,
        "events": events,
        "method_note": (
            "Each price_reaction is the REAL close price on/after that one event's "
            "date and at 1/5/10/20 trading days later, fetched live -- a factual "
            "record of what happened once, not a prediction and not an average "
            "across multiple events. A null offset means not enough trading days "
            "have elapsed yet since the event. Many other factors move a stock "
            "price besides the listed event; no causation is implied."
        ),
    }
