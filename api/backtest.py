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
from services.formula_composer_service import get_leaderboard, run_scan
from services.regime_router_service import get_best_for_regime, get_current_regime, run_regime_scan
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


@router.get("/backtest/{ticker}/walk-forward")
def backtest_walk_forward(ticker: str, strategy: str = "confluence_trend",
                           period: str = "2y", n_folds: int = 4):
    """2026-08-10 (P0 of the Quant Research Factory roadmap) -- out-of-
    sample validation, see services/backtest_service.py's
    run_walk_forward() docstring for the full methodology (N chronological
    folds + a 70/30 in-sample/out-of-sample split + a heuristic
    overfitting-risk flag)."""
    if not _SYMBOL_RE.match(ticker):
        return {"status": "error", "message": "無效嘅代號格式"}
    n_folds = max(2, min(12, n_folds))  # sane bounds -- too many folds on 2y of daily bars leaves each fold with almost no trades
    result = BacktestService.run_walk_forward(ticker, strategy=strategy, period=period, n_folds=n_folds)
    if "error" in result:
        return {"status": "error", "message": result["error"]}
    return {"status": "ok", "data": result}


@router.get("/formula-composer/{ticker}/scan")
def formula_composer_scan(ticker: str, period: str = "2y", n_folds: int = 4,
                           min_oos_trades: int = 5, top_n: int = 5):
    """2026-08-10 (P2 of the Quant Research Factory roadmap) -- runs
    services/formula_composer_service.py's small-scale combinatorial
    strategy scan (35 candidate combinations of 6 existing causal
    indicator primitives, each walk-forward-validated) against `ticker`
    and returns the top out-of-sample survivors. See that module's
    docstring for the full methodology and why this stays deliberately
    small rather than an exhaustive/genetic search."""
    if not _SYMBOL_RE.match(ticker):
        return {"status": "error", "message": "無效嘅代號格式"}
    n_folds = max(2, min(12, n_folds))
    top_n = max(1, min(20, top_n))
    min_oos_trades = max(1, min(50, min_oos_trades))
    result = run_scan(ticker, period=period, n_folds=n_folds, min_oos_trades=min_oos_trades, top_n=top_n)
    if "error" in result:
        return {"status": "error", "message": result["error"]}
    return {"status": "ok", "data": result}


@router.get("/formula-composer/leaderboard")
def formula_composer_leaderboard(symbol: str = None, limit: int = 20):
    """Reads the persisted formula_composer_candidates leaderboard --
    either one symbol's full last-scan table (best first) or, without a
    symbol, the most recently scanned rows across all symbols. Read-only,
    never triggers a fresh scan (use the /scan endpoint above for that)."""
    limit = max(1, min(100, limit))
    if symbol is not None and not _SYMBOL_RE.match(symbol):
        return {"status": "error", "message": "無效嘅代號格式"}
    rows = get_leaderboard(symbol=symbol, limit=limit)
    return {"status": "ok", "data": rows}


@router.get("/regime-router/{ticker}/current-regime")
def regime_router_current(ticker: str, lang: str = None):
    """2026-08-10 (P3 of the Quant Research Factory roadmap) -- current
    causal regime classification for `ticker`. See services/regime_
    router_service.py's module docstring for why this uses its own
    causal-only classifier rather than the live Confluence/Regime Belief
    engines (which depend on look-ahead-tainted swing-point inputs).

    2026-08-31: lang query param added and threaded through (AJ flagged
    mixed-language rendering -- see get_current_regime()'s docstring)."""
    if not _SYMBOL_RE.match(ticker):
        return {"status": "error", "message": "無效嘅代號格式"}
    result = get_current_regime(ticker, lang=lang)
    if "error" in result:
        return {"status": "error", "message": result["error"]}
    return {"status": "ok", "data": result}


@router.get("/regime-router/{ticker}/scan")
def regime_router_scan(ticker: str, period: str = "2y"):
    """Runs services/regime_router_service.py's regime-conditional scan:
    simulates all 35 formula_composer_service candidates over `ticker`'s
    full history, buckets each trade by the causal regime active at its
    entry bar, and persists per-(candidate, regime) stats. Call this once
    per symbol before using /best-for-regime below."""
    if not _SYMBOL_RE.match(ticker):
        return {"status": "error", "message": "無效嘅代號格式"}
    result = run_regime_scan(ticker, period=period)
    if "error" in result:
        return {"status": "error", "message": result["error"]}
    return {"status": "ok", "data": result}


@router.get("/regime-router/{ticker}/best-for-regime")
def regime_router_best(ticker: str, regime: str = None, min_trades: int = 5, lang: str = None):
    """Reads the persisted regime-conditional leaderboard. If `regime` is
    omitted, first computes the ticker's CURRENT regime (same as
    /current-regime above) and looks that up -- the actual "what should I
    use right now" answer this roadmap phase promised. Requires
    /scan to have been run for this symbol first.

    2026-08-31: lang query param added and threaded through to both
    get_current_regime() and get_best_for_regime() -- previously this
    endpoint had no lang param at all, so its "reason"/caveat text stayed
    hardcoded Cantonese no matter what language the calling page had
    selected (ai-analysis.html/chart-analysis.html's regime-router labels
    DO follow the page's selected language via data-i18n, which produced a
    visibly mixed-language result whenever a non-Chinese language was
    selected -- AJ flagged this directly)."""
    if not _SYMBOL_RE.match(ticker):
        return {"status": "error", "message": "無效嘅代號格式"}
    min_trades = max(1, min(50, min_trades))
    if not regime:
        current = get_current_regime(ticker, lang=lang)
        if "error" in current:
            return {"status": "error", "message": current["error"]}
        regime = current["regime"]
    result = get_best_for_regime(ticker, regime, min_trades=min_trades, lang=lang)
    return {"status": "ok", "data": result}
