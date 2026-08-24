"""2026-08-24 (AJ's Capital Flow Engine roadmap, Layer 7 -- "Probabilistic
K-Line Path Generator"): the highest-leverage piece identified during the
build-audit before this file existed -- every raw ingredient already
existed elsewhere in this codebase, real and validated, just never
combined into one Forecast Object:
  - services/monte_carlo_service.py already bootstraps real historical
    daily log-returns into simulated future paths, but only ever reported
    percentiles of the FINAL value, not a day-by-day band.
  - services/direction_probability_service.py already trains and
    BACKTEST-GATES a GradientBoostingClassifier's N-day up-probability
    (never serves an unvalidated model -- see its own honesty contract).
  - services/capital_flow_engine.py (2026-08-24, same day) already
    computes a global capital-flow/liquidity regime reading.

This module does not introduce a new statistical method -- it runs the
same bootstrap-of-real-returns technique as monte_carlo_service.py (kept
as a local, day-by-day-band variant rather than importing that module's
function, since simulate() there only returns the FINAL-value percentiles
and reshaping its return contract would risk breaking stress-lab.html,
which already depends on the exact shape documented in that file), then
presents it as a labeled Bear/Base/Bull fan chart -- the standard
central-bank "fan chart" convention (e.g. Bank of England GDP forecasts),
not an arbitrary tercile split. "Bull path" = the 90th percentile of
simulated paths, "Base path" = the median (50th percentile), "Bear path"
= the 10th percentile -- i.e. an honest statement that "80% of simulated
outcomes fall between the Bear and Bull lines", never a fabricated
"Bull probability = 43%" figure invented independently of the simulation
itself.

The one place a genuinely independent number is layered in is
direction_probability_service's validated ML up-probability, shown
side-by-side as a labeled cross-check ("today's independently-trained,
backtested model separately estimates X% odds of a higher close") --
deliberately NOT mathematically fused into the bootstrap distribution
(that would require a defensible Bayesian-updating scheme this codebase
doesn't have and would risk manufacturing false precision). Two honest,
separately-labeled numbers beat one falsely-precise blended one.
"""
import logging
from typing import Dict, List, Optional

import numpy as np

from services.technical_analysis_service import fetch_ohlc_history

logger = logging.getLogger(__name__)

MIN_OBSERVATIONS = 100
DEFAULT_N_SIMULATIONS = 2000
MAX_HORIZON_DAYS = 60  # a "K-line path" is a near-term product -- capped well below monte_carlo_service's 756-day stress-test ceiling
BAND_PERCENTILES = {"bear": 10, "base": 50, "bull": 90}


def _simulate_day_by_day_bands(closes: np.ndarray, horizon_days: int, n_simulations: int) -> Optional[Dict]:
    """Bootstrap `n_simulations` paths from real historical daily log
    returns (same i.i.d.-resample method as monte_carlo_service.simulate,
    see that file's honesty notes on what this does and doesn't capture),
    but keeps the FULL per-day matrix so a percentile can be taken at
    every horizon day, not just the final one -- that's what turns a
    single ending-value distribution into an actual path/fan chart."""
    log_returns = np.diff(np.log(closes))
    log_returns = log_returns[np.isfinite(log_returns)]
    if len(log_returns) < MIN_OBSERVATIONS:
        return None

    last_close = float(closes[-1])
    rng = np.random.default_rng()
    sampled_returns = rng.choice(log_returns, size=(n_simulations, horizon_days), replace=True)
    cumulative_log_returns = np.cumsum(sampled_returns, axis=1)
    price_paths = last_close * np.exp(cumulative_log_returns)  # shape: (n_simulations, horizon_days)

    bands = {}
    for name, pct in BAND_PERCENTILES.items():
        # Percentile taken independently PER DAY across simulations, not
        # a single simulated path -- standard fan-chart construction, and
        # explicitly disclosed as such in the returned `method` field
        # (each day's percentile isn't necessarily the same simulation
        # run as the neighboring day's, so this is a band, not one
        # sampled trajectory).
        bands[name] = [round(float(v), 4) for v in np.percentile(price_paths, pct, axis=0)]

    return {
        "last_close": round(last_close, 4),
        "bear_path": bands["bear"],
        "base_path": bands["base"],
        "bull_path": bands["bull"],
        "n_real_observations": len(log_returns),
    }


def get_probabilistic_forecast(symbol: str, horizon_days: int = 5, n_simulations: int = DEFAULT_N_SIMULATIONS) -> Dict:
    """
    Returns the Forecast Object:
        {"available": True, "symbol": "...", "horizon_days": 5, "last_close": ...,
         "bear_path": [...], "base_path": [...], "bull_path": [...],
         "band_note": "80%嘅模擬結果落喺Bear/Bull之間...",
         "ml_cross_check": {"available": True/False, "up_probability_pct": ..., ...} | None,
         "capital_flow_context": {"score": ..., "direction": "..."} | None,
         "method": "...", "disclaimer": "..."}
        {"available": False, "message": "..."}
    """
    symbol = (symbol or "").upper().strip()
    if not symbol:
        return {"available": False, "message": "代號唔可以係空"}

    horizon_days = max(1, min(int(horizon_days or 5), MAX_HORIZON_DAYS))
    n_simulations = max(200, min(int(n_simulations or DEFAULT_N_SIMULATIONS), 5000))

    try:
        df = fetch_ohlc_history(symbol, period="2y", interval="1d")
    except Exception as e:
        return {"available": False, "message": f"攞唔到 {symbol} 嘅歷史數據：{e}"}

    if df is None or "Close" not in df.columns or len(df) < MIN_OBSERVATIONS + 1:
        return {"available": False, "message": f"{symbol} 嘅真實歷史數據唔夠（需要至少 {MIN_OBSERVATIONS} 個交易日）"}

    closes = df["Close"].astype(float).values
    sim = _simulate_day_by_day_bands(closes, horizon_days, n_simulations)
    if sim is None:
        return {"available": False, "message": f"{symbol} 有效歷史回報樣本唔夠"}

    # Independent ML cross-check -- lazy import, never blocks/breaks this
    # endpoint if unavailable (no trained model, failed its backtest gate,
    # or stale -- see direction_probability_service's own honesty gate).
    ml_cross_check = None
    try:
        from services.direction_probability_service import get_direction_probability
        ml_result = get_direction_probability(symbol, horizon_days=horizon_days)
        if ml_result.get("available"):
            ml_cross_check = {
                "available": True,
                "up_probability_pct": ml_result["up_probability_pct"],
                "holdout_accuracy_pct": ml_result["holdout_accuracy_pct"],
                "trained_at": ml_result["trained_at"],
            }
    except Exception:
        ml_cross_check = None

    # Capital Flow Engine regime context -- read-only cache peek (see that
    # module's own docstring), zero network cost, never blocks this call.
    capital_flow_context = None
    try:
        from services.capital_flow_engine import get_capital_flow_signal_for_confluence
        capital_flow_context = get_capital_flow_signal_for_confluence()
    except Exception:
        capital_flow_context = None

    return {
        "available": True,
        "symbol": symbol,
        "horizon_days": horizon_days,
        "last_close": sim["last_close"],
        "bear_path": sim["bear_path"],
        "base_path": sim["base_path"],
        "bull_path": sim["bull_path"],
        "band_note": (
            f"Bear/Base/Bull分別為{n_simulations}次真實歷史回報重組模擬嘅第10/50/90百分位——"
            f"即80%嘅模擬結果會落喺Bear同Bull路徑之間，並非固定機率預測。"
        ),
        "ml_cross_check": ml_cross_check,
        "capital_flow_context": capital_flow_context,
        "method": (
            "bootstrap resampling of real daily log returns (i.i.d.), "
            "day-by-day percentile band -- same underlying method as "
            "services/monte_carlo_service.py, extended to a per-day fan "
            "chart instead of a single ending-value distribution"
        ),
        "disclaimer": (
            "呢個係基於歷史統計嘅模擬區間，並非精確預測，唔構成投資建議。"
            "ml_cross_check（如有）係獨立訓練同backtest驗證過嘅模型，"
            "刻意唔同bootstrap區間混合計算，避免製造假精確度。"
        ),
    }
