from fastapi import APIRouter
from engines.anomaly_engine import AnomalyEngine
from services.dashboard_snapshot_service import get_dashboard_tickers, compute_snapshots

router = APIRouter()


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
            items.append({"ticker": s["ticker"], **result})

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
