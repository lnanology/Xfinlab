import re

from fastapi import APIRouter
from engines.anomaly_engine import AnomalyEngine
from services.dashboard_snapshot_service import get_dashboard_tickers, compute_snapshots
from services.anomaly_history_service import scan_last_30_days
from services.i18n import get_translations

router = APIRouter()

# Same ticker-format guard used by api/chart_analysis.py -- reject junk
# input cheaply before it ever reaches market_data_service. Includes "^"
# (2026-07-25 fix, see chart_analysis.py's _SYMBOL_RE comment) so world
# indices/VIX/Treasury-yield tickers (^HSI, ^GSPC, ^VIX, ^TNX etc.) aren't
# rejected before ever reaching yfinance.
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-=^]{1,12}$")


@router.get("/anomaly")
def anomaly(token: str = None):
    """
    Dashboard Anomaly Radar panel. Was previously always the exact
    same hardcoded reading (2.5M volume vs 900K average, +6.8% price
    change) for every user, every time, regardless of the real
    market. Now scans the user's real watchlist (or a small default
    basket) using live volume/price data per ticker.

    Response shape changed from a single flat anomaly object to a list
    of per-ticker results, since we're now scanning multiple tickers
    instead of one fixed one - dashboard.html's loadAnomaly() was
    updated to match.
    """
    tickers = get_dashboard_tickers(token)
    snapshots = compute_snapshots(tickers)

    items = []
    for s in snapshots:
        result = AnomalyEngine.detect(
            current_volume=s.get("volume", 0),
            average_volume=s.get("avg_volume", 1),
            price_change_pct=s.get("price_change_pct", 0.0),
        )
        if result["anomaly_count"] > 0:
            # 2026-08-10 (task #747-752): sparkline is already computed by
            # compute_snapshots() (dashboard_snapshot_service.py) -- pass it
            # straight through, zero extra fetches.
            items.append({"ticker": s["ticker"], "sparkline": s.get("sparkline", []), **result})

    severity_rank = {"HIGH": 2, "MEDIUM": 1, "NONE": 0}
    overall_severity = "NONE"
    for item in items:
        if severity_rank.get(item["severity"], 0) > severity_rank.get(overall_severity, 0):
            overall_severity = item["severity"]

    return {
        "scanned": len(snapshots),
        "severity": overall_severity,
        "items": items,
    }


@router.get("/anomaly/search/{ticker}")
def anomaly_search(ticker: str, lang: str = None):
    """
    Single-ticker anomaly check -- lets a user check ANY global ticker,
    separate from the batch watchlist scan above. Same AnomalyEngine
    math, same real volume/price data, just scoped to one symbol instead
    of the whole watchlist.

    Unlike the batch endpoint above (which only lists tickers that
    actually have an anomaly, since it's a "what needs my attention"
    radar), this ALWAYS returns a result even when severity is NONE --
    someone explicitly searching one ticker wants an honest "no anomaly
    detected" answer, not silence.

    2026-07-31 fix ("顯示「攞唔到 AAPL 嘅市場數據...」" regardless of UI
    language): both error messages below used to be hardcoded Traditional
    Chinese literals, so an English/Japanese/etc-mode user searching an
    unrecognized or data-unavailable ticker still saw raw Cantonese. Now
    accepts `lang` (same param anomaly.html already sends everywhere else
    via I18N.currentLang) and looks the two messages up from
    services/i18n.py's per-language dict, defaulting to the original
    Chinese text for zh-HK/zh-TW/unset lang -- these are plain UI strings
    (not AI-generated prose), so a direct dict lookup is simpler and more
    reliable here than the ai_language_instruction() prompt-steering
    pattern used for LLM endpoints elsewhere.
    """
    ticker = (ticker or "").strip().upper()
    tr = get_translations(lang) if lang and lang not in ("zh-HK", "zh-TW") else None

    if not ticker or not _SYMBOL_RE.match(ticker):
        msg = (tr or {}).get("anom_ticker_format_error") or "代號格式無效，請重新輸入。"
        return {"status": "error", "message": msg}

    snapshots = compute_snapshots([ticker])
    if not snapshots:
        msg = (tr or {}).get("anom_no_data_error") or "攞唔到 {ticker} 嘅市場數據，請確認代號正確。"
        return {"status": "error", "message": msg.replace("{ticker}", ticker)}

    s = snapshots[0]
    result = AnomalyEngine.detect(
        current_volume=s.get("volume", 0),
        average_volume=s.get("avg_volume", 1),
        price_change_pct=s.get("price_change_pct", 0.0),
    )

    return {
        "status": "ok",
        "ticker": s["ticker"],
        "sparkline": s.get("sparkline", []),
        **result,
    }


@router.get("/anomaly/history/{ticker}")
def anomaly_history(ticker: str):
    """
    Past 30 days of volume/price anomalies for a single ticker, with
    related news attached to each flagged day -- powers the "過去30日
    成交量異常" section on anomaly.html's single-ticker search result.

    Single-ticker only, by explicit design choice: extending this to the
    batch watchlist scan (GET /anomaly above) would multiply the yfinance
    + NewsAPI workload by the watchlist size, and was intentionally left
    out of scope for this feature.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker or not _SYMBOL_RE.match(ticker):
        return {"status": "error", "message": "代號格式無效，請重新輸入。"}

    return scan_last_30_days(ticker)
