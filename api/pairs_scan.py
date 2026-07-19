"""
Pairs Statistical Arbitrage Scanner API -- Stage 1 roadmap item 3
(2026-07-19). See services/pairs_arbitrage_service.py for the real
correlation/z-score methodology and its honest limitations.
"""

from fastapi import APIRouter

from services.pairs_arbitrage_service import scan_pair

router = APIRouter()


@router.post("/pairs-scan")
async def pairs_scan(body: dict):
    symbol_a = body.get("symbol_a", "")
    symbol_b = body.get("symbol_b", "")
    period = body.get("period", "6mo")
    result = scan_pair(symbol_a, symbol_b, period=period)
    return {"status": "ok", "data": result}
