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

router = APIRouter()

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-=^]{1,15}$")


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
