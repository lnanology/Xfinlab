"""
2026-08-10 (task #747-751, AJ: "所有卡片有資產的都加細K線小圖" -- 全站所有
頁). Shared backend helper for the last-N-closes array every asset card's
sparkline mini-chart needs (frontend rendering lives in js/sparkline.js,
XflSparkline.render()). Every consumer routes through
services.technical_analysis_service.fetch_ohlc_history() -- same
Alpaca-first/yfinance-fallback path already used everywhere else in this
codebase, so this introduces no new data source and no new licensing
surface (see services/license_registry.py).

Deliberately its own tiny module rather than living inside
dashboard_snapshot_service.py (which several *other* unrelated callers --
api/watchlist.py, api/company_compare.py -- would otherwise have needed to
import just for this one helper, pulling in its NewsEngine/RuleEngine/
ScoreEngine/RiskEngine dependency chain for no reason).
"""

import logging

from services.technical_analysis_service import fetch_ohlc_history

logger = logging.getLogger(__name__)


def get_recent_closes(ticker: str, days: int = 20, period: str = "1mo") -> list:
    """Best-effort last `days` closes, oldest-first, as plain floats ready
    for XflSparkline.render() on the frontend. Never raises -- a slow/failed
    OHLC fetch degrades to "no sparkline for this card" (falsy list, which
    js/sparkline.js's render() already treats as "draw nothing"), not a
    broken panel. `period` stays short (1 month of daily bars) since a
    sparkline only ever needs ~20 points -- no reason to pull 6 months of
    history per card the way chart-analysis.html's real chart does.
    """
    try:
        df = fetch_ohlc_history(ticker, period=period, interval="1d")
        if df is None or df.empty or "Close" not in df.columns:
            return []
        closes = df["Close"].dropna().tail(days).tolist()
        return [round(float(c), 4) for c in closes]
    except Exception as e:
        logger.info("Sparkline fetch failed for %s: %s", ticker, e)
        return []
