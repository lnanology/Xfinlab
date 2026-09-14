from fastapi import APIRouter
from engines.screener_engine import ScreenerEngine
from services.dashboard_snapshot_service import get_dashboard_tickers, compute_snapshots
from services.feature_flags_service import require_feature_enabled

router = APIRouter()


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
    tickers = get_dashboard_tickers(token)
    stocks = compute_snapshots(tickers)
    return ScreenerEngine.screen(stocks)
