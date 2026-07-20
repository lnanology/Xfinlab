"""
Monte Carlo Bootstrap Simulation -- Stage 3 roadmap item 2 (2026-07-19):
"歷史事件蒙地卡羅模擬" (historical-event Monte Carlo simulation).

Replaces api/stress_lab.py's PREVIOUS implementation, which asked an LLM
to "estimate" a loss percentage and recovery time for a hardcoded
historical-scenario description -- a real violation of this codebase's
core "never fabricate a number" principle (the old prompt literally
asked the model to invent a figure with zero grounding in actual price
data). That endpoint turned out to be dead code by the time this was
found: stress-lab.html stopped calling it back on 2026-07-11 in favor of
a transparent, clearly-labelled client-side calculation using assumed
per-strategy drawdown profiles (see that file's own inline comment/
disclaimer) -- so no live user was actually seeing the fabricated
numbers. This module is a genuine, new capability built to properly
fulfil the roadmap item, not just a bug fix: a REAL Monte Carlo
simulation grounded in a symbol's own real historical daily returns.

Method (stated honestly):
  1. Fetch real daily OHLCV for the requested symbol (same Alpaca-first/
     yfinance-fallback routing every other real-data feature in this
     codebase uses -- see services/technical_analysis_service.py).
  2. Compute real daily log returns from real historical closes.
  3. Bootstrap: resample `horizon_days` returns, WITH replacement,
     independently and identically distributed (i.i.d.) from that real
     historical return sample, `n_simulations` times, to build
     `n_simulations` simulated future price paths.
  4. Report percentiles (P5/P25/P50/P75/P95) of the simulated ending
     value and of each path's own max drawdown.

Honesty notes:
  - i.i.d. resampling does NOT preserve real-world volatility clustering
    or autocorrelation (a real historical crash's daily moves aren't
    independent of each other) -- a block-bootstrap would model that
    better, but at real added complexity. This is disclosed in the
    returned `method` field rather than silently overclaiming realism.
  - This simulates "what if the future looks statistically like this
    symbol's OWN recent real history", not any specific named historical
    crisis (2008/2020/2022) -- it's a different, complementary lens from
    stress-lab.html's own hardcoded historical-scenario cards, not a
    replacement for them.
  - Honestly returns unavailable when there isn't enough real history
    for a stable resample, rather than guessing.
"""

import logging
from typing import Dict, Optional

import numpy as np

from services.technical_analysis_service import fetch_ohlc_history

logger = logging.getLogger(__name__)

MIN_OBSERVATIONS = 100
DEFAULT_N_SIMULATIONS = 2000
MAX_HORIZON_DAYS = 756  # ~3 trading years -- a sane upper bound so a bad input can't trigger a huge resample
MAX_N_SIMULATIONS = 5000


def _max_drawdown_pct(cumulative_path: np.ndarray) -> float:
    """cumulative_path: array of cumulative portfolio VALUE (not returns)
    along one simulated path, starting at the initial amount. Returns the
    largest real peak-to-trough decline along that specific path, as a
    negative percentage."""
    running_peak = np.maximum.accumulate(cumulative_path)
    drawdowns = (cumulative_path - running_peak) / running_peak
    return float(drawdowns.min() * 100)


def simulate(
    symbol: str,
    amount: float,
    horizon_days: int = 252,
    n_simulations: int = DEFAULT_N_SIMULATIONS,
    period: str = "2y",
) -> Dict:
    """
    Returns:
        {"available": True, "symbol": str, "horizon_days": int,
         "n_simulations": int, "n_real_observations": int,
         "ending_value_p5": float, "ending_value_p25": float,
         "ending_value_p50": float, "ending_value_p75": float, "ending_value_p95": float,
         "max_drawdown_p50_pct": float, "max_drawdown_p5_pct": float,
         "method": "...", "note": "..."}
        {"available": False, "message": "..."} -- not enough real history,
            or the fetch itself failed
    """
    symbol = (symbol or "").upper().strip()
    if not symbol:
        return {"available": False, "message": "請輸入股票代號"}
    if amount is None or amount <= 0:
        return {"available": False, "message": "投入金額必須大於零"}

    horizon_days = max(1, min(int(horizon_days or 252), MAX_HORIZON_DAYS))
    n_simulations = max(100, min(int(n_simulations or DEFAULT_N_SIMULATIONS), MAX_N_SIMULATIONS))

    try:
        df = fetch_ohlc_history(symbol, period=period, interval="1d")
    except Exception as e:
        return {"available": False, "message": f"攞唔到 {symbol} 嘅歷史數據：{e}"}

    if df is None or "Close" not in df.columns or len(df) < MIN_OBSERVATIONS + 1:
        return {"available": False, "message": f"{symbol} 嘅真實歷史數據唔夠（需要至少 {MIN_OBSERVATIONS} 個交易日）"}

    closes = df["Close"].astype(float).values
    log_returns = np.diff(np.log(closes))
    log_returns = log_returns[np.isfinite(log_returns)]
    if len(log_returns) < MIN_OBSERVATIONS:
        return {"available": False, "message": f"{symbol} 有效歷史回報樣本唔夠"}

    rng = np.random.default_rng()
    # Draw an (n_simulations x horizon_days) matrix of real historical
    # daily log returns, sampled i.i.d. with replacement -- vectorized so
    # even MAX_N_SIMULATIONS x MAX_HORIZON_DAYS stays fast.
    sampled_returns = rng.choice(log_returns, size=(n_simulations, horizon_days), replace=True)
    cumulative_log_returns = np.cumsum(sampled_returns, axis=1)
    value_paths = amount * np.exp(cumulative_log_returns)  # shape: (n_simulations, horizon_days)

    ending_values = value_paths[:, -1]
    # Prepend the real starting amount to each path so day-0 (before any
    # simulated move) is included in the drawdown calculation.
    full_paths = np.concatenate([np.full((n_simulations, 1), amount), value_paths], axis=1)
    max_drawdowns = np.array([_max_drawdown_pct(full_paths[i]) for i in range(n_simulations)])

    percentiles = [5, 25, 50, 75, 95]
    ending_pcts = np.percentile(ending_values, percentiles)
    drawdown_p50, drawdown_p5 = np.percentile(max_drawdowns, [50, 5])

    return {
        "available": True,
        "symbol": symbol,
        "horizon_days": horizon_days,
        "n_simulations": n_simulations,
        "n_real_observations": len(log_returns),
        "starting_amount": amount,
        "ending_value_p5": round(float(ending_pcts[0]), 2),
        "ending_value_p25": round(float(ending_pcts[1]), 2),
        "ending_value_p50": round(float(ending_pcts[2]), 2),
        "ending_value_p75": round(float(ending_pcts[3]), 2),
        "ending_value_p95": round(float(ending_pcts[4]), 2),
        "max_drawdown_p50_pct": round(float(drawdown_p50), 2),
        "max_drawdown_p5_pct": round(float(drawdown_p5), 2),
        "method": "bootstrap resampling of real daily log returns (i.i.d., not block-bootstrap)",
        "note": (
            f"基於 {symbol} 過去 {len(log_returns)} 個真實交易日嘅日回報，"
            f"獨立同分布抽樣重組 {n_simulations} 次模擬未來 {horizon_days} 個交易日嘅可能路徑。"
            "呢個方法假設每日回報互相獨立，唔會保留真實市場嘅波動聚集／自相關特性，"
            "亦唔對應任何特定歷史事件（例如2008／2020），僅反映呢隻股票自身近期統計特性，"
            "並非精確預測，不構成投資建議。"
        ),
    }
