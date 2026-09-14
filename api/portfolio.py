import logging

from fastapi import APIRouter
from engines.portfolio_engine import PortfolioEngine
from services.dashboard_snapshot_service import get_dashboard_tickers, compute_snapshots
from services.feature_flags_service import require_feature_enabled

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/portfolio")
def portfolio(token: str = None):
    """
    Dashboard Portfolio Allocation panel. Was previously always the
    same 3 hardcoded stocks (NVDA/AAPL/MSFT) with fixed fake scores
    for every user, regardless of what they actually track. Now
    allocates across the user's real watchlist (or a small default
    basket if logged out / no watchlist yet), weighted by each
    ticker's real market_score computed from live data.
    """
    # 2026-09-14: enforce admin.html's "portfolio" toggle (previously
    # persisted but never checked -- see services/feature_flags_service.py).
    require_feature_enabled("portfolio")
    # 2026-09-14 hardening (site-wide pain-points audit finding #2 --
    # "backend error handling"): no try/except previously -- a bad
    # watchlist entry or market-data hiccup on any one ticker took down
    # the whole Portfolio Allocation panel with a raw 500. Falls back to
    # PortfolioEngine.allocate()'s own "no stocks" shape ({"portfolio":
    # [], "cash": 100}) -- honest "nothing to allocate this time" rather
    # than a broken panel.
    try:
        tickers = get_dashboard_tickers(token)
        snapshots = compute_snapshots(tickers)
        screener_results = [
            {"ticker": s["ticker"], "final_score": s["market_score"]}
            for s in snapshots
        ]
        result = PortfolioEngine.allocate(screener_results)
        # 2026-08-10 (task #747-750): PortfolioEngine.allocate() only keeps
        # ticker/allocation -- attach each row's sparkline (already computed by
        # compute_snapshots() above) back on afterward rather than threading it
        # through the engine, so the allocation math itself stays untouched.
        spark_map = {s["ticker"]: s.get("sparkline", []) for s in snapshots}
        for row in result.get("portfolio", []):
            row["sparkline"] = spark_map.get(row["ticker"], [])
        return result
    except Exception:
        logger.exception("portfolio: allocation failed")
        return {"portfolio": [], "cash": 100}
