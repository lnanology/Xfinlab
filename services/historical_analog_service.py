"""
Historical Analog Service -- Tier 3 layered-UX addition (2026-07-18),
built INSTEAD OF a "Decision Lab" macro-shock slider ("what if Fed cuts
25bps?", "what if oil rises?").

This codebase has no real quantitative macro-sensitivity model anywhere
(no historical regression linking Fed decisions / oil prices / USD moves
to any specific ticker's returns). Shipping a slider that pretends to
re-forecast a ticker under a hypothetical macro shock without one would
be exactly the kind of fabricated-looking-precise number this codebase's
"never fabricate" convention (see services/backtest_service.py's module
docstring, api/pipeline_api.py's probability-framing disclaimer, etc.)
exists to prevent.

What this does instead, honestly: buckets EVERY historical bar of the
actual ticker by (trend direction, relative volatility), finds every
prior bar in the SAME bucket as today, and reports what really happened
over the following `forward_days` each of those times. Every number
traces to real historical closes -- nothing here is a forecast, and
nothing models a hypothetical event that hasn't happened. This is
retrospective statistical characterization of one real ticker's own
history, the same spirit as services/backtest_service.py's honest
win-rate/drawdown reporting.
"""

import logging
from typing import Dict

import numpy as np

from services.technical_analysis_service import TechnicalAnalysisService

logger = logging.getLogger(__name__)

_svc = TechnicalAnalysisService

WARMUP_BARS = 60
FORWARD_DAYS_DEFAULT = 10


def find_analogs(symbol: str, period: str = "2y", interval: str = "1d",
                  forward_days: int = FORWARD_DAYS_DEFAULT) -> Dict:
    try:
        df = _svc._fetch_history(symbol, period, interval)
    except Exception as e:
        return {"error": f"攞唔到 {symbol} 嘅歷史數據：{str(e)}"}

    if df is None or df.empty or len(df) < WARMUP_BARS + forward_days + 10:
        return {"error": f"{symbol} 歷史數據不足，無法推算歷史類比（需要至少 {WARMUP_BARS + forward_days + 10} 條K線）"}

    df = df.dropna()
    closes, highs, lows = df["Close"], df["High"], df["Low"]
    n = len(closes)

    sma50 = closes.rolling(min(50, n)).mean()
    trend_dir = np.where(closes.values > sma50.values, "偏多", "偏空")

    atr14 = _svc._atr(highs, lows, closes, 14)
    atr_pct = (atr14 / closes) * 100
    # Whole-sample median as the high/low volatility threshold -- this is
    # a RETROSPECTIVE characterization of this ticker's own history (like
    # a backtest's summary stats), not a live per-bar trading signal, so
    # using the full sample to define "relatively high/low vol for this
    # ticker" is an honest read, not a look-ahead-tainted one.
    vol_median = float(np.nanmedian(atr_pct.values))
    vol_bucket = np.where(atr_pct.values >= vol_median, "高波動", "低波動")

    current_trend = trend_dir[-1]
    current_vol = vol_bucket[-1]
    current_label = f"{current_trend}・{current_vol}"

    closes_v = closes.values
    forward_returns = []
    match_dates = []
    # Exclude the most recent `forward_days` bars (no forward data exists
    # yet for those) and bars before WARMUP_BARS (indicators not fully
    # populated).
    for i in range(WARMUP_BARS, n - forward_days):
        if trend_dir[i] == current_trend and vol_bucket[i] == current_vol:
            entry_price = float(closes_v[i])
            exit_price = float(closes_v[i + forward_days])
            if entry_price > 0:
                forward_returns.append((exit_price - entry_price) / entry_price * 100)
                match_dates.append(str(df.index[i].date()))

    if not forward_returns:
        return {
            "symbol": symbol.upper(),
            "regime_label": current_label,
            "forward_days": forward_days,
            "match_count": 0,
            "note": "呢隻股票歷史上未出現過同現時相似嘅（趨勢＋波動）組合，無法提供歷史類比統計。",
        }

    arr = np.array(forward_returns)
    win_rate = round(float((arr > 0).sum() / len(arr) * 100), 1)

    return {
        "symbol": symbol.upper(),
        "regime_label": current_label,
        "forward_days": forward_days,
        "match_count": len(forward_returns),
        "win_rate_pct": win_rate,
        "avg_forward_return_pct": round(float(arr.mean()), 2),
        "median_forward_return_pct": round(float(np.median(arr)), 2),
        "best_forward_return_pct": round(float(arr.max()), 2),
        "worst_forward_return_pct": round(float(arr.min()), 2),
        "sample_dates": match_dates[-5:],
        "methodology": (
            f"以「{current_label}」呢個組合（趨勢方向＋相對高低波動）搵返 {symbol.upper()} "
            f"過去所有出現過相似情況嘅日子，睇返之後 {forward_days} 個交易日嘅實際表現。"
            "呢個係歷史統計讀數，並非對未來嘅預測或者模型推算，亦非投資建議。"
        ),
    }
