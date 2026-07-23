"""
Step 3 of the Strategy Intelligence roadmap (2026-07-18) -- exposes
services/backtest_service.py's real historical backtesting over HTTP.

Same symbol-format validation pattern as api/anomaly.py/api/chart_
analysis.py's ticker routes (letters/digits/./-/=/^ only, capped length)
to reject anything that isn't a plausible ticker before it reaches
yfinance/Alpaca.
"""

import re

from fastapi import APIRouter

from services.backtest_service import BacktestService
from services.track_record_service import get_track_record

router = APIRouter()

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-=^]{1,15}$")


@router.get("/track-record")
def track_record():
    """Homepage 'Track Record' section data -- see
    services/track_record_service.py's module docstring for the full
    methodology (fixed 8-ticker basket, confluence_trend strategy, 24h
    cache). Always returns status ok with whatever was last successfully
    computed; symbols_tested==0 only if every backtest failed (e.g. data
    provider outage), which the frontend should treat as "not available
    yet" rather than an error."""
    return {"status": "ok", "data": get_track_record()}


@router.get("/backtest/{ticker}")
def backtest_ticker(ticker: str, strategy: str = "confluence_trend", period: str = "2y"):
    if not _SYMBOL_RE.match(ticker):
        return {"status": "error", "message": "無效嘅代號格式"}
    result = BacktestService.run(ticker, strategy=strategy, period=period)
    if "error" in result:
        return {"status": "error", "message": result["error"]}
    return {"status": "ok", "data": result}


@router.get("/backtest/{ticker}/compare")
def backtest_compare(ticker: str, period: str = "2y"):
    if not _SYMBOL_RE.match(ticker):
        return {"status": "error", "message": "無效嘅代號格式"}
    result = BacktestService.compare(ticker, period=period)
    if "error" in result:
        return {"status": "error", "message": result["error"]}
    return {"status": "ok", "data": result}
