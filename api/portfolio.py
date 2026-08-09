from fastapi import APIRouter
from engines.portfolio_engine import PortfolioEngine
from services.dashboard_snapshot_service import get_dashboard_tickers, compute_snapshots

router = APIRouter()


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
