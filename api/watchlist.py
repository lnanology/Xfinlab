from fastapi import APIRouter, HTTPException
from services.watchlist_service import WatchlistService
from services.market_data_service import MarketDataService
from backend.auth.jwt_handler import verify_token

router = APIRouter()
market_svc = MarketDataService()

@router.post("/watchlist/add/{ticker}")
def add_to_watchlist(ticker: str, token: str):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return WatchlistService.add(payload["id"], ticker)

@router.delete("/watchlist/remove/{ticker}")
def remove_from_watchlist(ticker: str, token: str):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return WatchlistService.remove(payload["id"], ticker)

@router.get("/watchlist")
def get_watchlist(token: str):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    items = WatchlistService.get_all(payload["id"])
    
    # 加入即時價格
    results = []
    for item in items:
        try:
            data = market_svc.get_stock_data(item["ticker"])
            results.append({
                "ticker": item["ticker"],
                "price": data.get("price", 0),
                "trend": data.get("trend", "neutral"),
                "added_at": item["added_at"]
            })
        except:
            results.append({
                "ticker": item["ticker"],
                "price": 0,
                "trend": "unknown",
                "added_at": item["added_at"]
            })
    
    return {"status": "ok", "watchlist": results}
