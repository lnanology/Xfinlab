"""
30-day historical volume/price anomaly scan for a single ticker, with
related news attached to each flagged day.

Scope note: this deliberately only supports single-ticker lookups
(services.anomaly_history_service.scan_last_30_days), matching the
site's existing single-ticker "/api/anomaly/search/{ticker}" endpoint.
It does NOT touch or extend the batch watchlist scan in api/anomaly.py
("/api/anomaly") -- running a 30-day, per-day history pull across an
entire watchlist would be a much heavier yfinance workload, and the
user explicitly chose single-ticker-search-only scope for this feature.

Honesty note on "time": yfinance's history(period=...) only returns
DAILY bars -- there is no reliable intraday timestamp available across
a rolling 30-day window (Yahoo caps intraday intervals like 1m/5m to a
very short lookback). So every flagged day's "time" field below is
labeled "收市 (Market Close)" rather than inventing a fake intraday
timestamp.
"""
from datetime import datetime, timedelta

# 2026-07-18 data-compliance pass: was a direct `yfinance` call, now
# routed through TechnicalAnalysisService's Alpaca-first/yfinance-
# fallback fetcher (see services/technical_analysis_service.py's
# fetch_ohlc_history() docstring) so this reduces yfinance exposure the
# same way the Chart/Research Engines already do, for free.
try:
    from services.technical_analysis_service import fetch_ohlc_history
except Exception:
    fetch_ohlc_history = None

from services.news_service import NewsService

# Same thresholds as engines/anomaly_engine.py's AnomalyEngine.detect(),
# reused directly (not reimplemented) so a "spike" means the same thing
# here as it does everywhere else on the site.
from engines.anomaly_engine import AnomalyEngine

# Trailing window (in trading days) used to compute each day's "average
# volume" baseline -- 20 trading days is roughly one calendar month,
# matches common technical-analysis convention (e.g. 20-day volume MA).
_TRAILING_WINDOW = 20

# How many of the flagged days (most recent first) get news attached.
# News lookups are a network call per day, so this is capped even if
# the caller passes a larger max_news_days.
_MAX_NEWS_DAYS_HARD_CAP = 10


def scan_last_30_days(ticker: str, attach_news: bool = True, max_news_days: int = 5):
    """
    Scan the last 30 calendar days of daily bars for `ticker`, flag any
    day whose volume/price move trips AnomalyEngine's thresholds, and
    (optionally) attach related news headlines for the most recent
    flagged days.

    Returns:
        {
          "status": "ok" | "error",
          "message": str (only when status == "error"),
          "ticker": str,
          "days_scanned": int,
          "flagged": [
            {
              "date": "YYYY-MM-DD",
              "time": "收市 (Market Close)",
              "volume": float,
              "avg_volume": float,
              "price_change_pct": float,
              "news": [ {title, source, published_at, url}, ... ],
              **AnomalyEngine.detect() fields (volume_ratio, anomalies,
                anomaly_count, severity)
            }, ...
          ]  # sorted newest-first
        }
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return {"status": "error", "message": "代號格式無效，請重新輸入。", "ticker": ticker, "flagged": []}

    if fetch_ohlc_history is None:
        return {"status": "error", "message": "市場數據服務暫時無法使用。", "ticker": ticker, "flagged": []}

    try:
        # 3mo gives enough trailing history to compute a real 20-day
        # average volume baseline even for the earliest day inside the
        # last-30-calendar-day window (which itself needs ~22 trading
        # days, plus 20 more trading days of lookback before that).
        hist = fetch_ohlc_history(ticker, period="3mo")
    except Exception as e:
        return {"status": "error", "message": f"攞唔到 {ticker} 嘅歷史數據: {e}", "ticker": ticker, "flagged": []}

    if hist is None or hist.empty or len(hist) < 2:
        return {"status": "error", "message": f"攞唔到 {ticker} 嘅歷史數據，請確認代號正確。", "ticker": ticker, "flagged": []}

    hist = hist.sort_index()
    cutoff = datetime.now() - timedelta(days=30)

    rows = list(hist.itertuples())
    flagged = []

    for i, row in enumerate(rows):
        row_date = row.Index.to_pydatetime().replace(tzinfo=None)
        if row_date < cutoff:
            continue
        if i == 0:
            continue  # no prior close to compute a price-change % against

        # Trailing average volume, excluding the day itself (avoids the
        # spike day inflating its own baseline).
        start = max(0, i - _TRAILING_WINDOW)
        trailing = rows[start:i]
        if not trailing:
            continue
        avg_volume = sum(r.Volume for r in trailing) / len(trailing)
        if avg_volume <= 0:
            continue

        current_volume = float(row.Volume)
        prev_close = float(rows[i - 1].Close)
        if prev_close <= 0:
            continue
        price_change_pct = round((float(row.Close) - prev_close) / prev_close * 100, 2)

        result = AnomalyEngine.detect(
            current_volume=current_volume,
            average_volume=avg_volume,
            price_change_pct=price_change_pct,
        )
        if result["anomaly_count"] == 0:
            continue

        flagged.append({
            "date": row_date.strftime("%Y-%m-%d"),
            "time": "收市 (Market Close)",
            "volume": current_volume,
            "avg_volume": round(avg_volume, 2),
            "news": [],
            **result,
        })

    flagged.sort(key=lambda d: d["date"], reverse=True)

    if attach_news and flagged:
        news_limit = min(max(max_news_days, 0), _MAX_NEWS_DAYS_HARD_CAP)
        if news_limit > 0:
            try:
                news_service = NewsService()
            except Exception:
                news_service = None

            if news_service is not None:
                for day in flagged[:news_limit]:
                    spike_date = datetime.strptime(day["date"], "%Y-%m-%d")
                    from_date = (spike_date - timedelta(days=1)).strftime("%Y-%m-%d")
                    to_date = (spike_date + timedelta(days=1)).strftime("%Y-%m-%d")
                    try:
                        day["news"] = news_service.get_company_news(
                            ticker, from_date=from_date, to_date=to_date, page_size=3
                        )
                    except Exception:
                        day["news"] = []

    return {
        "status": "ok",
        "ticker": ticker,
        "days_scanned": len([r for r in rows if r.Index.to_pydatetime().replace(tzinfo=None) >= cutoff]),
        "flagged": flagged,
        # 2026-08-10 (task #747-752, "所有卡片有資產的都加細K線小圖"): last
        # 20 closes for the shared js/sparkline.js mini-chart -- `hist` is
        # already sitting in memory from the fetch above, so this is a free
        # slice, zero extra network calls.
        "sparkline": [round(float(c), 4) for c in hist["Close"].dropna().tail(20).tolist()],
    }
