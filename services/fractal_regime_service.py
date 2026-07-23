"""
Fractal Market Structure / Regime Transition Signal -- Stage 2 roadmap
item 3 (2026-07-19): "市況轉換偵測延伸" (extending regime detection with
fractal geometry / a market self-similarity measure).

RegimeDetector (backend/alpha/regime_detector.py) classifies the CURRENT
snapshot from trend/volatility/volume -- it has no notion of whether the
market's underlying character (trending vs mean-reverting vs pure random
walk) is itself shifting. This module computes the Hurst exponent -- a
real, well-established statistic from fractal/time-series analysis
(Hurst, 1951; rescaled-range or "R/S" analysis) -- from real daily close
prices, and compares a recent window against a prior one to flag when the
market looks like it's transitioning from choppy/mean-reverting toward
persistent/trending behaviour (or vice versa).

What the Hurst exponent means (stated honestly, no overclaiming):
  H ~ 0.5   -- price changes look like an uncorrelated random walk
  H > 0.5   -- persistent/trending: an up move tends to be followed by
               another up move (positive autocorrelation)
  H < 0.5   -- anti-persistent/mean-reverting: an up move tends to be
               followed by a down move

This is a classical statistical estimator, not a proprietary or invented
metric, but it is a rough, noisy one on financial time series -- the
literature itself treats R/S-estimated Hurst values as indicative, not
precise. Consistent with this codebase's standard, this module:
  - Only runs on real OHLC history (services/technical_analysis_service.
    fetch_ohlc_history()), same source as realized_vol.py and
    pairs_arbitrage_service.py.
  - Returns None/unavailable honestly when there isn't enough real
    history for a stable multi-window R/S regression, rather than
    guessing.
  - Surfaces as an optional SECONDARY flag ("TREND_TRANSITION_WATCH"),
    mirroring how RegimeDetector.classify() already attaches
    "TREND_REVERSAL_WATCH" from a Market Structure CHOCH event -- it
    does NOT change the primary regime label or get folded into the
    Stage 1 Bayesian regime_belief_service likelihood, so it can't
    regress that engine's already-validated convergence behaviour.
"""

import math
from typing import Dict, Optional

import numpy as np

from services.technical_analysis_service import fetch_ohlc_history

# R/S analysis needs several non-overlapping windows of varying size to
# regress log(R/S) against log(window_size) -- fewer than this and the
# regression slope (the Hurst estimate) is too noisy to report honestly.
MIN_OBSERVATIONS = 100
# Window sizes (in trading days) used for the R/S regression -- a
# standard geometric spread, not fitted/tuned.
_WINDOW_SIZES = [10, 20, 30, 50, 75, 100]

PERSISTENT_THRESHOLD = 0.55
MEAN_REVERTING_THRESHOLD = 0.45


def _rescaled_range(returns: np.ndarray, window: int) -> Optional[float]:
    """Average rescaled range R/S over non-overlapping `window`-sized
    chunks of `returns`. Returns None if there isn't at least one full
    chunk."""
    n_chunks = len(returns) // window
    if n_chunks < 1:
        return None
    rs_values = []
    for i in range(n_chunks):
        chunk = returns[i * window: (i + 1) * window]
        mean = chunk.mean()
        deviations = np.cumsum(chunk - mean)
        r = deviations.max() - deviations.min()
        s = chunk.std(ddof=1)
        if s > 0:
            rs_values.append(r / s)
    if not rs_values:
        return None
    return float(np.mean(rs_values))


def hurst_exponent(closes: np.ndarray) -> Optional[float]:
    """
    closes: array of real daily close prices (chronological order).
    Returns the Hurst exponent estimated via classical R/S analysis
    (log-log regression of rescaled range vs. window size), or None if
    there isn't enough real data for a stable estimate.
    """
    if closes is None or len(closes) < MIN_OBSERVATIONS + 1:
        return None
    log_returns = np.diff(np.log(closes))
    log_returns = log_returns[np.isfinite(log_returns)]

    valid_windows = [w for w in _WINDOW_SIZES if len(log_returns) // w >= 1]
    if len(valid_windows) < 3:
        # Need at least 3 (window_size, R/S) points for a meaningful
        # regression slope -- fewer than that isn't an honest estimate.
        return None

    log_ws, log_rs = [], []
    for w in valid_windows:
        rs = _rescaled_range(log_returns, w)
        if rs and rs > 0:
            log_ws.append(math.log(w))
            log_rs.append(math.log(rs))

    if len(log_ws) < 3:
        return None

    slope, _intercept = np.polyfit(log_ws, log_rs, 1)
    return round(float(slope), 3)


def _classify_persistence(h: float) -> str:
    if h > PERSISTENT_THRESHOLD:
        return "TRENDING_PERSISTENT"
    if h < MEAN_REVERTING_THRESHOLD:
        return "MEAN_REVERTING"
    return "RANDOM_WALK"


def detect_transition_signal(symbol: str, period: str = "1y") -> Dict:
    """
    Compares the Hurst exponent of a recent window (most recent
    ~MIN_OBSERVATIONS observations) against an earlier window of the same
    size (the observations immediately before it) to flag a real,
    measured shift in the market's persistence character.

    Returns:
        {"available": True, "recent_hurst": float, "prior_hurst": float,
         "recent_label": str, "prior_label": str,
         "transition_watch": bool, "note": str}
        {"available": False, "message": "..."} -- not enough real history
    """
    try:
        df = fetch_ohlc_history(symbol, period=period, interval="1d")
    except Exception as e:
        return {"available": False, "message": f"攞唔到 {symbol} 嘅歷史數據：{e}"}

    if df is None or "Close" not in df.columns or len(df) < MIN_OBSERVATIONS * 2 + 1:
        return {"available": False, "message": f"{symbol} 嘅真實歷史數據唔夠（需要至少 {MIN_OBSERVATIONS * 2 + 1} 個交易日）"}

    closes = df["Close"].astype(float).values
    recent_window = closes[-(MIN_OBSERVATIONS + 1):]
    prior_window = closes[-(MIN_OBSERVATIONS * 2 + 1):-MIN_OBSERVATIONS]

    recent_h = hurst_exponent(recent_window)
    prior_h = hurst_exponent(prior_window)
    if recent_h is None or prior_h is None:
        return {"available": False, "message": f"{symbol} 嘅 Hurst 指數計算唔穩定，數據唔夠"}

    recent_label = _classify_persistence(recent_h)
    prior_label = _classify_persistence(prior_h)

    # The specific transition the roadmap asked to detect: market was NOT
    # trending before, and now looks like it is.
    transition_watch = (
        prior_label != "TRENDING_PERSISTENT" and recent_label == "TRENDING_PERSISTENT"
    )

    return {
        "available": True,
        "recent_hurst": recent_h,
        "prior_hurst": prior_h,
        "recent_label": recent_label,
        "prior_label": prior_label,
        "transition_watch": transition_watch,
        "note": (
            "Hurst指數由真實歷史收市價經典R/S分析估算，用嚟量度市場走勢嘅"
            "持續性（隨機遊走 vs 趨勢延續 vs 均值回歸），並非精確科學，"
            "僅供研究參考。"
        ),
    }
