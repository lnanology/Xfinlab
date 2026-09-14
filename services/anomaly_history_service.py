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
from services.i18n import localized_text

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

# 2026-09-14 addition (AJ: "量縮至量放，怎表達？" -- after adding
# engines/anomaly_engine.py's single-day volume_contraction/
# consolidation_signal, he asked how to express the actual multi-day
# TRANSITION -- several quiet days followed by a volume release -- since
# that's the real tradeable "量縮後放量突破" setup, not just "today is
# quiet" or "today is a spike" in isolation. AnomalyEngine.detect() only
# ever sees one day at a time, so this can't live there; it needs the
# whole daily_series this function already builds while scanning.
# _QUIET_RATIO_MAX (0.7) is deliberately looser than AnomalyEngine's
# strict 0.5x volume_contraction threshold -- a real multi-day basing
# phase rarely has EVERY single day under 0.5x, so requiring that would
# make _QUIET_DAYS consecutive days almost never trigger. _BREAKOUT_RATIO_MIN
# (1.5) is deliberately looser than AnomalyEngine's 2.0x volume_spike
# threshold for the same reason -- the day volume genuinely starts
# releasing is usually before it fully doubles.
_QUIET_DAYS = 3
_QUIET_RATIO_MAX = 0.7
_BREAKOUT_RATIO_MIN = 1.5


def _detect_contraction_breakouts(daily_series):
    """
    daily_series: oldest-first list of {"date", "volume_ratio",
    "price_change_pct"} for every scanned day (not just anomaly-flagged
    ones -- a quiet day with volume_ratio 0.6 never trips AnomalyEngine's
    0.5x threshold on its own, but still counts towards a quiet streak
    here).

    Returns a list of {type, breakout_date, quiet_period_start,
    quiet_period_end, quiet_days, breakout_volume_ratio,
    breakout_price_change_pct, direction, detail} -- one per breakout day
    immediately preceded by _QUIET_DAYS consecutive quiet days, sorted
    oldest-first (caller re-sorts newest-first alongside `flagged`).
    """
    signals = []
    for i in range(_QUIET_DAYS, len(daily_series)):
        window = daily_series[i - _QUIET_DAYS:i]
        if not all(d["volume_ratio"] < _QUIET_RATIO_MAX for d in window):
            continue
        today = daily_series[i]
        if today["volume_ratio"] <= _BREAKOUT_RATIO_MIN:
            continue
        direction = "up" if today["price_change_pct"] >= 0 else "down"
        signals.append({
            "type": "contraction_breakout",
            "breakout_date": today["date"],
            "quiet_period_start": window[0]["date"],
            "quiet_period_end": window[-1]["date"],
            "quiet_days": _QUIET_DAYS,
            "breakout_volume_ratio": today["volume_ratio"],
            "breakout_price_change_pct": today["price_change_pct"],
            "direction": direction,
            "detail": (
                f"{_QUIET_DAYS} quiet days (volume below {_QUIET_RATIO_MAX}x average, "
                f"{window[0]['date']} to {window[-1]['date']}) followed by a "
                f"{today['volume_ratio']}x volume breakout, price {direction} "
                f"{abs(today['price_change_pct'])}% -- possible 量縮後放量突破"
            ),
        })
    return signals


def scan_last_30_days(ticker: str, attach_news: bool = True, max_news_days: int = 5, lang: str = None):
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
        msg = localized_text("anom_ticker_format_error", lang)
        return {"status": "error", "message": msg, "ticker": ticker, "flagged": [], "contraction_breakouts": []}

    if fetch_ohlc_history is None:
        return {"status": "error", "message": localized_text("anom_history_service_unavailable", lang), "ticker": ticker, "flagged": [], "contraction_breakouts": []}

    try:
        # 3mo gives enough trailing history to compute a real 20-day
        # average volume baseline even for the earliest day inside the
        # last-30-calendar-day window (which itself needs ~22 trading
        # days, plus 20 more trading days of lookback before that).
        hist = fetch_ohlc_history(ticker, period="3mo")
    except Exception as e:
        msg = localized_text("anom_history_fetch_error", lang).replace("{ticker}", ticker).replace("{error}", str(e))
        return {"status": "error", "message": msg, "ticker": ticker, "flagged": [], "contraction_breakouts": []}

    if hist is None or hist.empty or len(hist) < 2:
        msg = localized_text("anom_history_no_data_error", lang).replace("{ticker}", ticker)
        return {"status": "error", "message": msg, "ticker": ticker, "flagged": [], "contraction_breakouts": []}

    hist = hist.sort_index()
    cutoff = datetime.now() - timedelta(days=30)

    rows = list(hist.itertuples())
    flagged = []
    # Every scanned day's volume_ratio/price_change_pct, oldest-first --
    # feeds _detect_contraction_breakouts() below, which needs quiet days
    # that never individually trip AnomalyEngine's thresholds (so never
    # end up in `flagged`) to detect the multi-day transition.
    daily_series = []

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
        daily_series.append({
            "date": row_date.strftime("%Y-%m-%d"),
            "volume_ratio": result["volume_ratio"],
            "price_change_pct": price_change_pct,
        })

        if result["anomaly_count"] == 0:
            continue

        flagged.append({
            "date": row_date.strftime("%Y-%m-%d"),
            "time": localized_text("anom_market_close_label", lang),
            "volume": current_volume,
            "avg_volume": round(avg_volume, 2),
            "news": [],
            **result,
        })

    flagged.sort(key=lambda d: d["date"], reverse=True)
    contraction_breakouts = _detect_contraction_breakouts(daily_series)
    contraction_breakouts.sort(key=lambda s: s["breakout_date"], reverse=True)

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
        # 2026-09-14 addition -- see _detect_contraction_breakouts() above.
        # Separate top-level field rather than folded into `flagged`: a
        # contraction-breakout is a property of a DATE RANGE (quiet_period
        # + breakout day together), not a single day's anomaly reading, so
        # it doesn't fit `flagged`'s one-day-per-entry shape.
        "contraction_breakouts": contraction_breakouts,
        # 2026-08-10 (task #747-752, "所有卡片有資產的都加細K線小圖"): last
        # 20 closes for the shared js/sparkline.js mini-chart -- `hist` is
        # already sitting in memory from the fetch above, so this is a free
        # slice, zero extra network calls.
        "sparkline": [round(float(c), 4) for c in hist["Close"].dropna().tail(20).tolist()],
    }
