"""
Pairs Statistical Arbitrage Scanner -- Stage 1 roadmap item 3
(2026-07-19): "Pairs 統計套利掃描器".

Research tool, NOT an auto-trading signal: monitors the real historical
price relationship between two tickers and flags when today's spread has
moved unusually far from its own recent historical norm.

Method (stated honestly, matching this codebase's existing standard of
labelling methodology rather than overclaiming):
  1. Fetch real daily closes for both tickers over the same lookback
     window via services/technical_analysis_service.fetch_ohlc_history()
     (the same Alpaca-first/yfinance-fallback routing every other real-
     data feature in this codebase uses).
  2. Align the two series on shared trading dates only.
  3. Compute the log price ratio log(close_a / close_b) each day -- the
     standard "spread" definition for a pairs trade.
  4. z-score = (today's log ratio - its own historical mean) / its own
     historical standard deviation, over the SAME lookback window.
  5. Correlation = Pearson correlation of the two tickers' DAILY RETURNS
     (not raw price levels, which correlate spuriously whenever both
     simply trend in the same direction) -- a real, standard measure of
     how tightly the pair actually co-moves.

This is a correlation + z-score divergence scan, NOT a full
cointegration test (e.g. Engle-Granger/ADF) -- a truly cointegrated pair
needs a formal stationarity test on the residual, which this doesn't run.
Labelled honestly in the API response and the UI copy so nobody mistakes
"high correlation + wide z-score" for "statistically proven mean-
reverting pair".
"""

import math
from typing import Dict

import numpy as np
import pandas as pd

from services.technical_analysis_service import fetch_ohlc_history

MIN_OVERLAPPING_DAYS = 30


def _align(df_a: pd.DataFrame, df_b: pd.DataFrame):
    a = df_a[["Close"]].rename(columns={"Close": "a"})
    b = df_b[["Close"]].rename(columns={"Close": "b"})
    merged = a.join(b, how="inner").dropna()
    return merged


def scan_pair(symbol_a: str, symbol_b: str, period: str = "6mo") -> Dict:
    symbol_a = (symbol_a or "").upper().strip()
    symbol_b = (symbol_b or "").upper().strip()
    if not symbol_a or not symbol_b:
        return {"status": "error", "available": False, "message": "請輸入兩個股票代號"}
    if symbol_a == symbol_b:
        return {"status": "error", "available": False, "message": "請輸入兩個唔同嘅股票代號"}

    try:
        df_a = fetch_ohlc_history(symbol_a, period=period, interval="1d")
        df_b = fetch_ohlc_history(symbol_b, period=period, interval="1d")
    except Exception as e:
        return {"status": "error", "available": False, "message": f"攞唔到歷史數據：{e}"}

    if df_a is None or df_b is None or df_a.empty or df_b.empty:
        return {"status": "ok", "available": False, "message": f"{symbol_a} 或 {symbol_b} 冇足夠歷史數據"}

    merged = _align(df_a, df_b)
    if len(merged) < MIN_OVERLAPPING_DAYS:
        return {
            "status": "ok", "available": False,
            "message": f"{symbol_a}／{symbol_b} 重疊嘅真實交易日只有 {len(merged)} 日，少於分析需要嘅 {MIN_OVERLAPPING_DAYS} 日",
        }

    log_ratio = np.log(merged["a"] / merged["b"])
    mean_ratio = float(log_ratio.mean())
    std_ratio = float(log_ratio.std(ddof=1))
    current_ratio = float(log_ratio.iloc[-1])
    z_score = round((current_ratio - mean_ratio) / std_ratio, 2) if std_ratio > 0 else 0.0

    returns_a = merged["a"].pct_change().dropna()
    returns_b = merged["b"].pct_change().dropna()
    common_len = min(len(returns_a), len(returns_b))
    correlation = float(np.corrcoef(returns_a.iloc[-common_len:], returns_b.iloc[-common_len:])[0, 1]) if common_len > 1 else None
    correlation = round(correlation, 3) if correlation is not None and not math.isnan(correlation) else None

    if abs(z_score) < 1:
        divergence = "NORMAL"       # 正常範圍
    elif abs(z_score) < 2:
        divergence = "ELEVATED"     # 偏離增加
    else:
        divergence = "EXTREME"      # 極端偏離

    richer = symbol_a if z_score > 0 else symbol_b
    cheaper = symbol_b if z_score > 0 else symbol_a

    return {
        "status": "ok",
        "available": True,
        "symbol_a": symbol_a,
        "symbol_b": symbol_b,
        "overlapping_days": len(merged),
        "z_score": z_score,
        "correlation": correlation,
        "divergence": divergence,
        "richer_symbol": richer if abs(z_score) >= 1 else None,
        "cheaper_symbol": cheaper if abs(z_score) >= 1 else None,
        "current_log_ratio": round(current_ratio, 4),
        "mean_log_ratio": round(mean_ratio, 4),
        "methodology_note": "相關係數／z-score偏離掃描，並非正式協整(cointegration)檢定，僅供研究參考，不構成交易建議。",
    }
