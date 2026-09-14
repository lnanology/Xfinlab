import logging

from fastapi import APIRouter
from engines.screener_engine import ScreenerEngine
from services.dashboard_snapshot_service import get_dashboard_tickers, compute_snapshots
from services.feature_flags_service import require_feature_enabled

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/screener")
def screener(token: str = None):
    """
    Dashboard Screener panel. Was previously always the same 3
    hardcoded stocks (AAPL/NVDA/TSLA) with hand-picked fake scores for
    every user. Now scores the user's real watchlist (or a small
    default basket if logged out / no watchlist yet) from live market
    + news data, then ranks/filters through the existing
    ScreenerEngine formula.
    """
    # 2026-09-14: enforce admin.html's "screener" toggle (previously
    # persisted but never checked -- see services/feature_flags_service.py).
    require_feature_enabled("screener")
    # 2026-09-14 hardening (site-wide pain-points audit finding #2 --
    # "backend error handling"): no try/except previously -- a bad
    # watchlist entry or market-data hiccup on any one ticker took down
    # the whole Screener panel with a raw 500. Falls back to an honest
    # "nothing passed the filter this time" shape instead.
    try:
        tickers = get_dashboard_tickers(token)
        stocks = compute_snapshots(tickers)
        return ScreenerEngine.screen(stocks)
    except Exception:
        logger.exception("screener: screen failed")
        return {"count": 0, "results": []}
