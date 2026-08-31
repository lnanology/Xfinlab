"""
Regime Router Service -- P3 of the Quant Research Factory roadmap
(2026-08-10), the final phase of this roadmap (P0 real cost/walk-forward
validation -> P1 Prediction Ledger -> P2 Formula Composer -> this).

What this answers: "given the market regime `symbol` is in RIGHT NOW,
which of services/formula_composer_service.py's 35 composed candidates
has historically performed best DURING THAT SAME REGIME" -- not "what's
the best candidate overall" (that's already formula_composer_service.
get_leaderboard()) and not "what regime am I in" in isolation (that's
services/regime_belief_service.get_belief(), a live-only Bayesian
tracker -- see below for why this module doesn't just reuse it).

Why a new causal regime classifier instead of reusing existing ones:
research done before writing this module found that backend.alpha.
regime_detector.RegimeDetector.classify() itself is a pure, memoryless
function of a dict (no look-ahead problem in the classifier itself), but
every real call site in this codebase builds that dict's `trend_direction`/
`trend_confidence_pct` from TechnicalAnalysisService._confluence(), which
includes support/resistance and Fibonacci signals built from fractal swing
points that need FUTURE bars to confirm -- exactly the look-ahead bias
services/backtest_service.py's own module docstring documents and
excludes (see its lines on why the live Confluence Engine's swing-point
signal is left out of backtesting entirely). services/regime_belief_
service.py inherits the same problem (same evidence inputs) plus is
inherently stateful/sequential per symbol, built for live use, not replay.
services/fractal_regime_service.py's Hurst-exponent transition detector IS
causal but is snapshot-only (always "now", not parameterized by a
historical bar index) and only a secondary watch flag with 3 buckets.

So: this module computes its own trend_direction/trend_confidence_pct
input to RegimeDetector.classify() from BacktestService._confluence_score()
-- the exact same causal, look-ahead-free weighted signal blend
_signal_confluence_trend() itself is built from (see that method's
docstring: "same weights, minus the support/resistance/Fibonacci signals").
volatility comes from ATR14/close's own trailing 126-bar percentile rank
(pandas .rolling().rank(pct=True), itself strictly backward-looking).
volume_ratio is ind["volume"][i] / ind["volume_sma20"][i], already computed
causally by BacktestService._compute_causal_indicators(). structure_event
and hurst_signal are left None at every bar (both would reintroduce the
same look-ahead problem) -- RegimeDetector.classify() already documents
both as optional with neutral fallbacks, so this is not a silent gap, it's
using the classifier within its own documented causal-safe subset.

These three causal numbers feed RegimeDetector.classify() UNCHANGED --
reusing its existing 9-bucket labels/thresholds rather than inventing a
new taxonomy, the same "reuse what already exists" principle P2's
formula_composer_service applied to indicator primitives.

Method: for a symbol, fetch history + compute ind ONCE (same pattern as
formula_composer_service.run_scan()), classify every bar's regime once,
then re-run each of the 35 composer candidates' FULL-HISTORY simulation
(BacktestService._simulate() with no entry_range restriction) and bucket
each trade's outcome by the regime active at its entry_idx. Persisted to
a sqlite table keyed by (symbol, label, regime) so get_best_for_regime()
is a fast read, not a re-scan, once run_regime_scan() has been called for
a symbol.

Honesty caveats (same spirit as every other module in this roadmap):
bucketing an already-small trade count by 9 regimes spreads it even
thinner -- most (candidate, regime) cells on most symbols will have too
few trades to mean anything, which is why get_best_for_regime() enforces
its own min-trade floor and returns "insufficient data" honestly rather
than a spurious "best" pick from 1-2 trades.
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from backend.alpha.regime_detector import RegimeDetector
from services.backtest_service import WARMUP_BARS, BacktestService
from services.formula_composer_service import generate_candidates
from services.technical_analysis_service import TechnicalAnalysisService
from services.i18n import get_translations

logger = logging.getLogger(__name__)

_svc = TechnicalAnalysisService

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

VOLATILITY_PERCENTILE_WINDOW = 126  # ~6 trading months, same order of magnitude as a 2y backtest period


def classify_regime_series(df: pd.DataFrame, ind: Dict) -> List[Optional[str]]:
    """
    Returns a list of length len(df): regime label string (one of
    RegimeDetector's 9 buckets, or "LOW_LIQUIDITY") at every bar from
    WARMUP_BARS onward, None before that (indicators aren't warmed up yet
    -- same convention as BacktestService's own WARMUP_BARS gating).
    """
    n = len(df)
    closes = ind["close"]
    atr14 = np.asarray(ind["atr14"], dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        atr_pct = atr14 / np.asarray(closes, dtype=float)
    vol_percentile = (
        pd.Series(atr_pct)
        .rolling(VOLATILITY_PERCENTILE_WINDOW, min_periods=30)
        .rank(pct=True) * 100
    ).values

    volume = np.asarray(ind["volume"], dtype=float)
    volume_sma20 = np.asarray(ind["volume_sma20"], dtype=float)

    regimes: List[Optional[str]] = [None] * n
    for i in range(WARMUP_BARS, n):
        score = BacktestService._confluence_score(i, ind)
        if score is None:
            direction, confidence_pct = None, 0.0
        elif score >= 0:
            direction, confidence_pct = "偏多", abs(score)
        else:
            direction, confidence_pct = "偏空", abs(score)

        vp = vol_percentile[i]
        volatility = float(vp) if not np.isnan(vp) else 50.0

        vr = volume[i] / volume_sma20[i] if volume_sma20[i] and not np.isnan(volume_sma20[i]) and volume_sma20[i] > 0 else None

        result = RegimeDetector.classify({
            "volatility": volatility,
            "trend_direction": direction,
            "trend_confidence_pct": confidence_pct,
            "volume_ratio": vr,
        })
        regimes[i] = result["regime"]

    return regimes


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS regime_router_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            label TEXT NOT NULL,
            regime TEXT NOT NULL,
            trade_count INTEGER NOT NULL,
            win_rate_pct REAL,
            avg_return_pct REAL,
            scanned_at TEXT DEFAULT (datetime('now')),
            UNIQUE(symbol, label, regime)
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def _persist_regime_row(symbol: str, label: str, regime: str, trade_count: int,
                         win_rate_pct: Optional[float], avg_return_pct: Optional[float]):
    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO regime_router_candidates
               (symbol, label, regime, trade_count, win_rate_pct, avg_return_pct, scanned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(symbol, label, regime) DO UPDATE SET
                 trade_count=excluded.trade_count,
                 win_rate_pct=excluded.win_rate_pct,
                 avg_return_pct=excluded.avg_return_pct,
                 scanned_at=excluded.scanned_at""",
            (symbol, label, regime, trade_count, win_rate_pct, avg_return_pct,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    except Exception:
        logger.exception("regime_router.persist failed for %s / %s / %s", symbol, label, regime)
    finally:
        conn.close()


def run_regime_scan(symbol: str, period: str = "2y", interval: str = "1d") -> Dict:
    """
    Fetches `symbol` once, computes causal indicators + a per-bar regime
    label once, then simulates all 35 composer candidates over the FULL
    history (no walk-forward folding here -- this phase is about regime-
    conditional bucketing of trades, not out-of-sample validation; P2's
    scan already did that filtering for "is this candidate trustworthy at
    all"). Every (candidate, regime) combination with at least one trade
    is persisted; get_best_for_regime() applies its own min-trade floor at
    read time.
    """
    symbol = (symbol or "").upper().strip()
    if not symbol:
        return {"error": "缺少代號"}

    try:
        df = _svc._fetch_history(symbol, period, interval)
    except Exception as e:
        return {"error": f"攞唔到 {symbol} 嘅歷史數據：{str(e)}"}

    if df is None or df.empty or len(df) < WARMUP_BARS + 10:
        return {"error": f"{symbol} 歷史數據不足，無法做regime分析（需要至少 {WARMUP_BARS + 10} 條K線）"}

    df = df.dropna()
    closes, highs, lows, volume = df["Close"], df["High"], df["Low"], df["Volume"]
    ind = BacktestService._compute_causal_indicators(closes, highs, lows, volume)
    regimes = classify_regime_series(df, ind)

    candidates = generate_candidates()
    regime_counts: Dict[str, int] = {}
    rows_written = 0

    for cand in candidates:
        trades = BacktestService._simulate(df, ind, cand["signal_fn"])
        by_regime: Dict[str, List[Dict]] = {}
        for t in trades:
            entry_idx = t.get("entry_idx")
            regime = regimes[entry_idx] if entry_idx is not None and entry_idx < len(regimes) else None
            if regime is None:
                continue
            by_regime.setdefault(regime, []).append(t)
            regime_counts[regime] = regime_counts.get(regime, 0) + 1

        for regime, regime_trades in by_regime.items():
            stats = BacktestService._compute_stats(regime_trades)
            _persist_regime_row(
                symbol, cand["label"], regime,
                stats.get("trade_count", 0) or 0,
                stats.get("win_rate_pct"), stats.get("avg_return_pct"),
            )
            rows_written += 1

    return {
        "symbol": symbol,
        "period": period,
        "candidates_scanned": len(candidates),
        "regime_rows_written": rows_written,
        "regime_bar_counts": regime_counts,
        "caveats": [
            "每個(組合,regime)配對嘅交易次數再進一步拆細，好多配對得幾單交易，統計參考價值有限——請睇 get_best_for_regime() 嘅 min_trades 過濾。",
            "regime分類用緊因果（唔睇未來）嘅簡化訊號估算，同即時Confluence Engine用嘅完整訊號（包含支持/阻力）唔完全一樣，可能有落差。",
            "呢個只係歷史配對統計，唔係實時交易建議，過去表現不代表將來結果。",
        ],
    }


def get_best_for_regime(symbol: str, regime: str, min_trades: int = 5, lang: str = None) -> Dict:
    """Reads the persisted leaderboard for `symbol`, filtered to `regime`,
    ranked by avg_return_pct, requiring at least `min_trades` trades in
    that specific (candidate, regime) cell. Returns {"available": False,
    "reason": ...} honestly if nothing clears the bar, rather than
    returning a best-of-nothing pick.

    2026-08-31 fix (AJ flagged mixed-language rendering on ai-analysis.html/
    chart-analysis.html -- the "Current regime: ..." label was following the
    page's selected UI language while this function's reason/caveat text
    stayed hardcoded Cantonese regardless of caller): lang param added,
    mirroring services/historical_analog_service.py's is_zh_default/
    get_translations(lang)/_t() pattern exactly. No lang passed (or zh-HK/
    zh-TW/zh-CN) keeps the original Cantonese text -- zero behavior change
    for existing callers that don't pass lang."""
    is_zh_default = not lang or lang in ("zh-HK", "zh-TW", "zh-CN")
    tr = None if is_zh_default else get_translations(lang)

    def _t(key, fallback):
        return tr.get(key, fallback) if tr else fallback

    symbol = (symbol or "").upper().strip()
    conn = _get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM regime_router_candidates
               WHERE symbol = ? AND regime = ? AND trade_count >= ?
               ORDER BY avg_return_pct DESC""",
            (symbol, regime, min_trades),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {
            "available": False,
            "symbol": symbol,
            "regime": regime,
            "reason": _t(
                "regime_router_reason_insufficient",
                "暫時未有足夠數據（少於{min_trades}單交易）去揀選呢個regime表現最好嘅組合，"
                "請先用 run_regime_scan() 掃描呢隻股票，或者呢隻股票喺呢個regime出現嘅交易次數太少。",
            ).format(min_trades=min_trades),
        }

    best = dict(rows[0])
    return {
        "available": True,
        "symbol": symbol,
        "regime": regime,
        "best_candidate": {
            "label": best["label"],
            "trade_count": best["trade_count"],
            "win_rate_pct": best["win_rate_pct"],
            "avg_return_pct": best["avg_return_pct"],
        },
        "runner_up_candidates": [
            {"label": r["label"], "trade_count": r["trade_count"],
             "win_rate_pct": r["win_rate_pct"], "avg_return_pct": r["avg_return_pct"]}
            for r in rows[1:6]
        ],
        "caveats": [
            _t("regime_router_caveat_sample", "細樣本統計學上唔可靠，請留意 trade_count。"),
            _t("regime_router_caveat_notadvice", "呢個係揀選歷史上喺呢個regime表現最好嘅已有組合，唔係即時交易訊號，唔係投資建議。"),
        ],
    }


def get_current_regime(symbol: str, lang: str = None) -> Dict:
    """
    Live convenience wrapper: computes just the LATEST bar's causal
    regime label (same classify_regime_series() logic, but only the last
    row is needed so this refetches a short history rather than a full
    backtest period). Intended as the "what regime is this symbol in
    right now" half of the router, to be read alongside get_best_for_
    regime(symbol, that_regime) for the full recommendation.

    2026-08-31: lang param added, same fix/rationale as get_best_for_
    regime() above.
    """
    is_zh_default = not lang or lang in ("zh-HK", "zh-TW", "zh-CN")
    tr = None if is_zh_default else get_translations(lang)

    def _t(key, fallback):
        return tr.get(key, fallback) if tr else fallback

    symbol = (symbol or "").upper().strip()
    if not symbol:
        return {"error": _t("regime_router_err_missing_symbol", "缺少代號")}
    try:
        df = _svc._fetch_history(symbol, "6mo", "1d")
    except Exception as e:
        return {"error": _t("analog_err_fetch", "攞唔到 {symbol} 嘅歷史數據：{error}").format(symbol=symbol, error=str(e))}
    if df is None or df.empty or len(df) < WARMUP_BARS + 5:
        return {"error": _t("regime_router_err_insufficient", "{symbol} 歷史數據不足，無法判斷現時regime").format(symbol=symbol)}
    df = df.dropna()
    closes, highs, lows, volume = df["Close"], df["High"], df["Low"], df["Volume"]
    ind = BacktestService._compute_causal_indicators(closes, highs, lows, volume)
    regimes = classify_regime_series(df, ind)
    current = regimes[-1]
    return {
        "symbol": symbol,
        "regime": current,
        "as_of_date": str(df.index[-1].date()),
        "note": "呢個regime判斷用緊因果（唔睇未來）嘅簡化訊號，可能同其他頁面用緊嘅即時Confluence/Regime Belief結果有落差——見services/regime_router_service.py模組說明。",
    }
