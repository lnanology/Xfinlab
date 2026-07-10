"""
Technical Analysis Service — computes indicators & structural levels from
REAL historical OHLC data (yfinance), instead of asking an AI model to
"eyeball" a chart image and guess numbers.

This is the numeric backbone for Chart Analysis MVP Phase 1:
    真實數據計算 RSI / MACD / Swing High-Low / 支撐阻力 / 0.618 Fibonacci

AI vision (see api/chart_analysis.py) is only used for the parts that
genuinely need a "human eye" — visual pattern recognition (雙頂/雙底/
頭肩頂底/三角收斂 etc.) — never for numeric price levels.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict, List, Optional


class TechnicalAnalysisService:

    def get_analysis(
        self,
        symbol: str,
        period: str = "6mo",
        interval: str = "1d",
    ) -> Dict:
        try:
            df = yf.Ticker(symbol).history(period=period, interval=interval)
        except Exception as e:
            return {"error": f"攞唔到 {symbol} 嘅歷史數據：{str(e)}"}

        if df is None or df.empty or len(df) < 20:
            return {"error": f"{symbol} 歷史數據不足，無法計算技術指標"}

        df = df.dropna()
        closes = df["Close"]
        highs = df["High"]
        lows = df["Low"]
        volume = df["Volume"]

        rsi = self._rsi(closes)
        macd_line, signal_line, hist = self._macd(closes)
        swing_highs, swing_lows = self._swing_points(highs, lows)
        support, resistance = self._support_resistance(
            swing_highs, swing_lows, float(closes.iloc[-1])
        )
        fib = self._fibonacci(swing_highs, swing_lows)

        last_close = round(float(closes.iloc[-1]), 2)
        ma_window = min(50, len(closes))
        ma50 = float(closes.rolling(ma_window).mean().iloc[-1])
        trend = "上升" if last_close > ma50 else "下降"

        avg_vol20 = volume.rolling(min(20, len(volume))).mean().iloc[-1]
        last_vol = float(volume.iloc[-1])
        vol_ratio = (
            round(last_vol / float(avg_vol20), 2)
            if avg_vol20 and avg_vol20 > 0
            else None
        )
        volume_desc = (
            f"最近成交量為20日均量嘅{vol_ratio}倍"
            + ("（放量）" if vol_ratio and vol_ratio >= 1.5 else "")
            if vol_ratio
            else "成交量數據不足"
        )

        return {
            "symbol": symbol.upper(),
            "last_close": last_close,
            "trend": trend,
            "rsi": round(float(rsi.iloc[-1]), 2) if not rsi.empty else None,
            "macd": {
                "macd_line": round(float(macd_line.iloc[-1]), 4),
                "signal_line": round(float(signal_line.iloc[-1]), 4),
                "histogram": round(float(hist.iloc[-1]), 4),
                "trend": "金叉/看漲" if hist.iloc[-1] > 0 else "死叉/看跌",
            },
            "support": support,
            "resistance": resistance,
            "fibonacci_0618": fib,
            "volume_ratio": vol_ratio,
            "volume_desc": volume_desc,
            "swing_highs": [round(float(x), 2) for x in swing_highs[-5:]],
            "swing_lows": [round(float(x), 2) for x in swing_lows[-5:]],
            "data_points": len(df),
            "period": period,
            "interval": interval,
        }

    # ---- indicators ----

    @staticmethod
    def _rsi(closes: pd.Series, period: int = 14) -> pd.Series:
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)

    @staticmethod
    def _macd(closes: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast = closes.ewm(span=fast, adjust=False).mean()
        ema_slow = closes.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        hist = macd_line - signal_line
        return macd_line, signal_line, hist

    @staticmethod
    def _swing_points(highs: pd.Series, lows: pd.Series, window: int = 5):
        """
        Deterministic fractal-style swing point detector: a swing high is a
        local max over `window` bars on each side, a swing low is a local
        min. No AI guessing involved — pure price-action math.
        """
        swing_highs: List[float] = []
        swing_lows: List[float] = []
        n = len(highs)
        for i in range(window, n - window):
            h_slice = highs.iloc[i - window : i + window + 1]
            l_slice = lows.iloc[i - window : i + window + 1]
            if highs.iloc[i] == h_slice.max():
                swing_highs.append(float(highs.iloc[i]))
            if lows.iloc[i] == l_slice.min():
                swing_lows.append(float(lows.iloc[i]))
        return swing_highs, swing_lows

    @staticmethod
    def _support_resistance(
        swing_highs: List[float],
        swing_lows: List[float],
        last_close: float,
        tolerance: float = 0.02,
    ):
        """
        Cluster nearby swing points into zones (within `tolerance` % of each
        other), then pick the nearest resistance zone above price and
        support zone below price. `touches` = how many times price
        respected that zone — a rough proxy for level strength.
        """

        def cluster(points: List[float]):
            if not points:
                return []
            pts = sorted(points)
            clusters = [[pts[0]]]
            for p in pts[1:]:
                if abs(p - clusters[-1][-1]) / clusters[-1][-1] <= tolerance:
                    clusters[-1].append(p)
                else:
                    clusters.append([p])
            return [
                {"level": round(sum(c) / len(c), 2), "touches": len(c)}
                for c in clusters
            ]

        high_clusters = cluster(swing_highs)
        low_clusters = cluster(swing_lows)

        resistance_candidates = sorted(
            [c for c in high_clusters if c["level"] >= last_close],
            key=lambda c: c["level"],
        )
        support_candidates = sorted(
            [c for c in low_clusters if c["level"] <= last_close],
            key=lambda c: -c["level"],
        )

        resistance = (
            resistance_candidates[0]
            if resistance_candidates
            else (high_clusters[-1] if high_clusters else None)
        )
        support = (
            support_candidates[0]
            if support_candidates
            else (low_clusters[0] if low_clusters else None)
        )

        return support, resistance

    @staticmethod
    def _fibonacci(
        swing_highs: List[float], swing_lows: List[float]
    ) -> Optional[Dict]:
        """
        0.618 / 0.5 / 0.382 retracement based on the most recent significant
        swing (highest high vs lowest low observed among detected swing
        points) — real price-derived levels, not AI estimates.
        """
        if not swing_highs or not swing_lows:
            return None
        swing_high = max(swing_highs)
        swing_low = min(swing_lows)
        diff = swing_high - swing_low
        if diff <= 0:
            return None
        return {
            "swing_high": round(swing_high, 2),
            "swing_low": round(swing_low, 2),
            "level_0618": round(swing_high - diff * 0.618, 2),
            "level_0500": round(swing_high - diff * 0.5, 2),
            "level_0382": round(swing_high - diff * 0.382, 2),
        }


technical_service = TechnicalAnalysisService()


def get_technical_analysis(
    symbol: str, period: str = "6mo", interval: str = "1d"
) -> Dict:
    return technical_service.get_analysis(symbol, period, interval)


if __name__ == "__main__":
    import json

    print(json.dumps(get_technical_analysis("AAPL"), indent=2, ensure_ascii=False))
