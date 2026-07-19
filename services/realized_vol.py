"""
Real annualized realized volatility -- Stage 1 Smart Beta / Bayesian
Regime addition (2026-07-19).

Several callers in this codebase (api/ai_analysis.py's RiskEngine input,
backend/alpha/feature_engine.py before its 2026-07-18 fix) used a crude
`volume_ratio * 15` stand-in for "volatility" rather than a real number
computed from price history. This module computes the real thing --
annualized standard deviation of daily log returns, the same textbook
definition backtest_service.py and engines/risk_engine.py already use
elsewhere in this codebase -- from the same OHLC history every other
real-data feature here already fetches via
services/technical_analysis_service.fetch_ohlc_history(). No new data
source, no fabricated number: if there isn't enough real history to
compute a stable estimate, this honestly returns None rather than
guessing.
"""

import math
from typing import Optional

import numpy as np
import pandas as pd

MIN_OBSERVATIONS = 10
TRADING_DAYS_PER_YEAR = 252


def annualized_volatility_pct(df: Optional[pd.DataFrame]) -> Optional[float]:
    """
    df: OHLC DataFrame as returned by
        services.technical_analysis_service.fetch_ohlc_history() (must
        have a 'Close' column). Returns annualized volatility as a 0-100+
        percentage, or None if there isn't enough real data to compute one.
    """
    if df is None or "Close" not in df.columns or len(df) < MIN_OBSERVATIONS + 1:
        return None
    closes = df["Close"].astype(float).values
    log_returns = np.diff(np.log(closes))
    log_returns = log_returns[np.isfinite(log_returns)]
    if len(log_returns) < MIN_OBSERVATIONS:
        return None
    daily_std = float(np.std(log_returns, ddof=1))
    annualized = daily_std * math.sqrt(TRADING_DAYS_PER_YEAR) * 100
    return round(annualized, 1)
