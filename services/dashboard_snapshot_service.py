"""
Shared helpers for dashboard.html's Screener/Portfolio/Anomaly panels.

Previously api/screener.py, api/portfolio.py and api/anomaly.py each
returned a fixed, hardcoded set of 3 stocks (AAPL/NVDA/TSLA) with
hand-picked fake scores -- every logged-in user saw the exact same
numbers regardless of what they actually watch, and the numbers never
changed with the real market. This module replaces that with a real
pipeline: pull the user's actual watchlist (falling back to a small
default basket for logged-out users or empty watchlists), then compute
each ticker's scores from real market data using the same
RuleEngine -> ScoreEngine -> NewsEngine -> RiskEngine pipeline already
live and tested in api/ai_analysis.py / api/full_analysis_v3.py.
"""

import time
from typing import List, Dict, Optional

from services.market_data_service import MarketDataService
from services.news_service import NewsService
from services.watchlist_service import WatchlistService
from services.sparkline_service import get_recent_closes
from engines.rule_engine import RuleEngine
from engines.score_engine import ScoreEngine
from engines.risk_engine import RiskEngine
from engines.news_engine import NewsEngine
from backend.auth.jwt_handler import verify_token

market_svc = MarketDataService()
news_svc = NewsService()

# Small, liquid, well-known basket shown to logged-out users or users
# with an empty watchlist. Not a recommendation -- just a reasonable
# default so the panels aren't empty before someone builds a watchlist.
DEFAULT_BASKET = ["AAPL", "MSFT", "GOOGL", "NVDA", "AMZN"]

MAX_TICKERS = 6

# 2026-09-14 addition (site-wide pain-points audit finding #3 --
# "performance"): compute_ticker_snapshot() below drives ALL THREE of
# api/anomaly.py, api/portfolio.py, api/screener.py, plus anomaly.py's
# single-ticker search -- every one of those page loads was hitting
# yfinance (services/market_data_service.py, which has no caching of its
# own) AND services/sparkline_service.py fresh, per ticker, on every single
# request. api/chart_analysis.py already solved this exact problem for its
# own endpoints with a module-level TTL cache; this brings the same pattern
# here rather than leaving this code path as the one place that never got
# it. 300s (5 min) matches chart_analysis.py's own TTL for the same
# yfinance-backed data -- short enough that "anomaly" detection and
# portfolio scores don't go meaningfully stale, long enough that a user
# refreshing the dashboard repeatedly (or several users sharing the same
# default basket) doesn't refetch identical data every time.
_SNAPSHOT_CACHE: dict = {}
_SNAPSHOT_CACHE_TTL_SECONDS = 300
_SNAPSHOT_CACHE_MAX_ENTRIES = 300


def _ttl_cache_get(store: dict, key: str, ttl: int):
    entry = store.get(key)
    if not entry:
        return None
    ts, value = entry
    if time.time() - ts > ttl:
        store.pop(key, None)
        return None
    return value


def _ttl_cache_set(store: dict, key: str, value, max_entries: int) -> None:
    if len(store) >= max_entries:
        oldest_key = min(store, key=lambda k: store[k][0])
        store.pop(oldest_key, None)
    store[key] = (time.time(), value)


def get_dashboard_tickers(token: Optional[str]) -> List[str]:
    """Resolve which tickers to show: the user's real watchlist if they
    have one, otherwise the default basket. Never fabricates a
    per-user list -- if there's no valid token or no watchlist items,
    it's honestly the shared default, not fake personalization."""
    if token:
        payload = verify_token(token)
        if payload:
            try:
                items = WatchlistService.get_all(payload["id"])
                tickers = [item["ticker"].upper() for item in items][:MAX_TICKERS]
                if tickers:
                    return tickers
            except Exception:
                pass
    return DEFAULT_BASKET


def compute_ticker_snapshot(ticker: str) -> Optional[Dict]:
    """Real market_score/news_score/risk_score for one ticker, computed
    from live data. Returns None if market data is unavailable for the
    symbol (e.g. bad ticker, data source failure) rather than
    fabricating a placeholder."""
    cache_key = (ticker or "").upper().strip()
    cached = _ttl_cache_get(_SNAPSHOT_CACHE, cache_key, _SNAPSHOT_CACHE_TTL_SECONDS)
    if cached is not None:
        return cached

    market = market_svc.get_stock_data(ticker)
    if not market or market.get("error"):
        return None

    volume_ratio = market.get("volume_ratio", 1.0)
    trend = market.get("trend", "neutral")
    breakout = market.get("breakout", False)
    sentiment = market.get("sentiment", "neutral")

    rule_scores = RuleEngine().evaluate({
        "volume_ratio": volume_ratio,
        "trend": trend,
        "breakout": breakout,
        "sentiment": sentiment,
    })
    score_result = ScoreEngine().calculate(rule_scores)
    market_score = min(100, round(score_result["total_score"], 2))

    try:
        raw_news = news_svc.get_company_news(ticker)
        news_result = NewsEngine.analyze([
            {"title": a.get("title", ""), "summary": a.get("title", "")}
            for a in raw_news[:5]
        ])
        news_score = round(news_result["score"], 2)
    except Exception:
        news_score = 50.0  # neutral fallback - no fake precision

    volatility = volume_ratio * 15
    risk_result = RiskEngine.calculate(
        volatility=volatility, event_risk=20, news_score=news_score
    )
    risk_score = round(risk_result["overall_risk"], 2)

    resolved_ticker = market.get("symbol", ticker.upper())
    result = {
        "ticker": resolved_ticker,
        "price": market.get("price", 0),
        "volume": market.get("volume", 0),
        "avg_volume": market.get("avg_volume", 0),
        "volume_ratio": volume_ratio,
        "price_change_pct": market.get("price_change_pct", 0.0),
        "market_score": market_score,
        "news_score": news_score,
        # No separate "strategy" signal computed here - reuse market_score
        # as the proxy, same as api/ai_analysis.py's tech_score does.
        "strategy_score": market_score,
        "risk_score": risk_score,
        # 2026-08-10 (task #747-751): last-20-closes for the shared
        # js/sparkline.js mini-chart -- feeds api/portfolio.py's Portfolio
        # Allocation panel and api/anomaly.py's batch scan, both of which
        # build their per-ticker items from this snapshot.
        "sparkline": get_recent_closes(resolved_ticker),
    }
    _ttl_cache_set(_SNAPSHOT_CACHE, cache_key, result, _SNAPSHOT_CACHE_MAX_ENTRIES)
    return result


def compute_snapshots(tickers: List[str]) -> List[Dict]:
    """Compute snapshots for a list of tickers, silently skipping any
    that fail (bad ticker / data source down) instead of erroring the
    whole panel."""
    results = []
    for t in tickers:
        snap = compute_ticker_snapshot(t)
        if snap:
            results.append(snap)
    return results
