"""
Technical Analysis Service — computes indicators & structural levels from
REAL historical OHLC data, instead of asking an AI model to "eyeball" a
chart image and guess numbers.

Data source: US-listed symbols use Alpaca Markets' free IEX feed when
ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are configured — Alpaca's data API
is free and its terms permit showing the data to end users (see
services/source_registry.py). Everything else (non-US symbols, or Alpaca
not configured / a request fails) falls back to yfinance, same as before.
This reduces — but does not eliminate — reliance on yfinance's
non-commercial-license grey area (see services/license_registry.py) without
requiring a paid data plan to ship today.

This is the numeric backbone for Chart Analysis MVP Phase 1:
    真實數據計算 RSI / MACD / Swing High-Low / 支撐阻力 / 0.618 Fibonacci

AI vision (see api/chart_analysis.py) is only used for the parts that
genuinely need a "human eye" — visual pattern recognition (雙頂/雙底/
頭肩頂底/三角收斂 etc.) — never for numeric price levels.
"""

import logging
import os
import re
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ALPACA_DATA_URL = "https://data.alpaca.markets/v2/stocks/bars"
ALPACA_PERIOD_DAYS = {"1mo": 30, "3mo": 90, "6mo": 182, "1y": 365, "2y": 730}
ALPACA_INTERVAL_TIMEFRAME = {"1d": "1Day", "1h": "1Hour"}

# Alpaca only lists US exchanges. A symbol with a dot-suffix (0700.HK,
# 2330.TW, 7203.T ...) is never a US ticker, so don't even try Alpaca for
# those — go straight to yfinance.
_US_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}$")


class TechnicalAnalysisService:

    def get_analysis(
        self,
        symbol: str,
        period: str = "6mo",
        interval: str = "1d",
    ) -> Dict:
        try:
            df = self._fetch_history(symbol, period, interval)
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

        rsi_last = round(float(rsi.iloc[-1]), 2) if not rsi.empty else None
        macd_hist_last = round(float(hist.iloc[-1]), 4)

        # ---- Phase 1 Indicator Intelligence Engine: additive indicators ----
        # New block, computed from the SAME already-fetched real df -- no
        # extra network calls needed. Kept as a separate "indicators"
        # sub-dict rather than flattened into the top level so this stays
        # 100% additive: nothing existing gets renamed or removed, so the
        # 5 other modules already calling get_technical_analysis() (market
        # _pulse, hero_showcase, pipeline_api, public_demo, chart_analysis)
        # keep working unchanged whether or not they read this new key.
        atr14_series = self._atr(highs, lows, closes, 14)
        atr14 = round(float(atr14_series.iloc[-1]), 4) if not atr14_series.empty else None
        bb_upper, bb_mid, bb_lower = self._bollinger(closes, 20, 2)
        bb_last = (
            {
                "upper": round(float(bb_upper.iloc[-1]), 2),
                "mid": round(float(bb_mid.iloc[-1]), 2),
                "lower": round(float(bb_lower.iloc[-1]), 2),
            }
            if not bb_upper.empty
            else None
        )
        obv_series = self._obv(closes, volume)
        obv_window = min(10, len(obv_series))
        obv_trend = None
        if len(obv_series) > obv_window:
            obv_trend = (
                "上升" if obv_series.iloc[-1] > obv_series.iloc[-obv_window] else "下降"
            )
        vwap_series = self._vwap(highs, lows, closes, volume)

        # ---- Step 2 (2026-07-18) Signal Engine upgrade: SuperTrend /
        # Ichimoku / Donchian / Keltner -- additive, same real df, no new
        # network calls. See each method's own docstring for the exact
        # causal math used.
        supertrend_series, supertrend_dir_series = self._supertrend(highs, lows, closes)
        supertrend_last = (
            {
                "value": round(float(supertrend_series.iloc[-1]), 2),
                "direction": "上升" if supertrend_dir_series.iloc[-1] == 1 else "下降",
            }
            if not supertrend_series.empty
            else None
        )

        tenkan, kijun, senkou_a, senkou_b = self._ichimoku(highs, lows, closes)
        ichimoku_last = None
        if not senkou_a.empty and not pd.isna(senkou_a.iloc[-1]) and not pd.isna(senkou_b.iloc[-1]):
            cloud_top = max(float(senkou_a.iloc[-1]), float(senkou_b.iloc[-1]))
            cloud_bottom = min(float(senkou_a.iloc[-1]), float(senkou_b.iloc[-1]))
            if last_close > cloud_top:
                cloud_position = "雲上（偏多結構）"
            elif last_close < cloud_bottom:
                cloud_position = "雲下（偏空結構）"
            else:
                cloud_position = "雲內（盤整）"
            ichimoku_last = {
                "tenkan": round(float(tenkan.iloc[-1]), 2) if not pd.isna(tenkan.iloc[-1]) else None,
                "kijun": round(float(kijun.iloc[-1]), 2) if not pd.isna(kijun.iloc[-1]) else None,
                "senkou_a": round(float(senkou_a.iloc[-1]), 2),
                "senkou_b": round(float(senkou_b.iloc[-1]), 2),
                "cloud_position": cloud_position,
            }

        donchian_upper, donchian_lower = self._donchian(highs, lows)
        donchian_last = (
            {
                "upper": round(float(donchian_upper.iloc[-1]), 2),
                "lower": round(float(donchian_lower.iloc[-1]), 2),
            }
            if not donchian_upper.empty and not pd.isna(donchian_upper.iloc[-1])
            else None
        )

        keltner_upper, keltner_mid, keltner_lower = self._keltner(closes, highs, lows)
        keltner_last = (
            {
                "upper": round(float(keltner_upper.iloc[-1]), 2),
                "mid": round(float(keltner_mid.iloc[-1]), 2),
                "lower": round(float(keltner_lower.iloc[-1]), 2),
            }
            if not keltner_upper.empty and not pd.isna(keltner_upper.iloc[-1])
            else None
        )

        indicators = {
            "ema20": round(float(self._ema(closes, 20).iloc[-1]), 2),
            "ema50": round(float(self._ema(closes, 50).iloc[-1]), 2) if len(closes) >= 2 else None,
            "sma20": round(float(self._sma(closes, 20).iloc[-1]), 2),
            "sma50": round(ma50, 2),
            "atr14": atr14,
            "bollinger": bb_last,
            "obv": round(float(obv_series.iloc[-1]), 0) if not obv_series.empty else None,
            "obv_trend": obv_trend,
            # Cumulative-since-fetch-window VWAP, not a true intraday
            # session VWAP (that needs tick-level same-day data we don't
            # fetch) -- labelled honestly so it isn't mistaken for one.
            "vwap": round(float(vwap_series.iloc[-1]), 2) if not vwap_series.empty else None,
            "supertrend": supertrend_last,
            "ichimoku": ichimoku_last,
            "donchian": donchian_last,
            "keltner": keltner_last,
        }

        confluence = self._confluence(
            trend=trend,
            rsi=rsi_last,
            macd_hist=macd_hist_last,
            last_close=last_close,
            support=support,
            resistance=resistance,
            fib=fib,
            bollinger=bb_last,
            obv_trend=obv_trend,
            supertrend=supertrend_last,
            ichimoku=ichimoku_last,
            donchian=donchian_last,
            keltner=keltner_last,
        )

        decision_levels = self._decision_levels(
            direction=confluence["direction"],
            last_close=last_close,
            support=support,
            resistance=resistance,
            atr14=atr14,
        )

        # ---- Phase 2 Market Structure Engine: additive, no extra data ----
        # fetch needed -- reuses the same chronologically-ordered swing_
        # highs/swing_lows already computed above for support/resistance.
        market_structure = self._market_structure(
            closes=closes, highs=highs, lows=lows,
            swing_highs=swing_highs, swing_lows=swing_lows,
        )

        return {
            "symbol": symbol.upper(),
            "ohlc": self._ohlc_series(df),
            "last_close": last_close,
            "trend": trend,
            "rsi": rsi_last,
            "macd": {
                "macd_line": round(float(macd_line.iloc[-1]), 4),
                "signal_line": round(float(signal_line.iloc[-1]), 4),
                "histogram": macd_hist_last,
                "trend": "金叉/看漲" if hist.iloc[-1] > 0 else "死叉/看跌",
            },
            "support": support,
            "resistance": resistance,
            "fibonacci_0618": fib,
            "volume_ratio": vol_ratio,
            "volume_desc": volume_desc,
            "swing_highs": [round(float(x), 2) for x in swing_highs[-5:]],
            "swing_lows": [round(float(x), 2) for x in swing_lows[-5:]],
            "indicators": indicators,
            "confluence": confluence,
            "decision_levels": decision_levels,
            "market_structure": market_structure,
            "data_points": len(df),
            "period": period,
            "interval": interval,
        }

    # ---- data source routing ----

    @staticmethod
    def _fetch_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
        """
        US-listed symbols try Alpaca first (free, commercial-use-friendly)
        when API keys are configured; everything else — non-US symbols,
        missing keys, or any Alpaca error — falls back to yfinance so
        behaviour never breaks because of this routing.
        """
        symbol_upper = symbol.upper().strip()
        alpaca_key = os.getenv("ALPACA_API_KEY_ID")
        alpaca_secret = os.getenv("ALPACA_API_SECRET_KEY")

        # Only attempt Alpaca for intervals it actually has a real mapping
        # for (see ALPACA_INTERVAL_TIMEFRAME). Previously this fell through
        # to `.get(interval, "1Day")`, which for an unmapped interval (e.g.
        # "1wk", added for the Phase 2 Multi-Timeframe Engine) would have
        # silently fetched DAILY bars mislabelled as whatever the caller
        # asked for. Better to skip Alpaca entirely and let yfinance
        # (which does support "1wk") handle it correctly.
        if (
            alpaca_key and alpaca_secret
            and _US_SYMBOL_RE.match(symbol_upper)
            and interval in ALPACA_INTERVAL_TIMEFRAME
        ):
            try:
                df = TechnicalAnalysisService._fetch_alpaca(
                    symbol_upper, period, interval, alpaca_key, alpaca_secret
                )
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                # Never hard-fail here — just fall through to yfinance below.
                # The warning already logged inside _fetch_alpaca (with the
                # X-Request-ID, if Alpaca returned one) is what you'd quote
                # in a support ticket to Alpaca if this keeps happening.
                logger.info(
                    "Alpaca fetch failed for %s, falling back to yfinance: %s",
                    symbol_upper, e,
                )

        return yf.Ticker(symbol).history(period=period, interval=interval)

    @staticmethod
    def _fetch_alpaca(
        symbol: str, period: str, interval: str, api_key: str, api_secret: str
    ) -> Optional[pd.DataFrame]:
        days = ALPACA_PERIOD_DAYS.get(period, 182)
        timeframe = ALPACA_INTERVAL_TIMEFRAME.get(interval, "1Day")
        end = datetime.utcnow()
        start = end - timedelta(days=days)

        res = requests.get(
            ALPACA_DATA_URL,
            params={
                "symbols": symbol,
                "timeframe": timeframe,
                "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "limit": 10000,
                "feed": "iex",  # Alpaca's free tier feed
            },
            headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
            },
            timeout=15,
        )
        # Alpaca stamps every response with a unique X-Request-ID. Their own
        # docs say to quote this in support tickets since it can't be looked
        # up any other way after the fact — so capture it before anything
        # else can raise, and log it alongside any failure.
        request_id = res.headers.get("X-Request-ID")

        try:
            res.raise_for_status()
        except requests.HTTPError as e:
            logger.warning(
                "Alpaca API error for %s: %s | X-Request-ID: %s "
                "(quote this ID if contacting Alpaca support)",
                symbol, e, request_id,
            )
            raise

        bars = res.json().get("bars", {}).get(symbol, [])
        if not bars:
            logger.info(
                "Alpaca returned no bars for %s | X-Request-ID: %s",
                symbol, request_id,
            )
            return None

        df = pd.DataFrame(bars)
        df["t"] = pd.to_datetime(df["t"])
        df = df.set_index("t").rename(
            columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"}
        )
        return df[["Open", "High", "Low", "Close", "Volume"]]

    # ---- charting ----

    @staticmethod
    def _ohlc_series(df: pd.DataFrame, max_bars: int = 120) -> List[Dict]:
        """
        Real OHLC bars (most recent `max_bars`) for client-side candlestick
        rendering (search-by-ticker flow, no screenshot needed). Capped at
        120 bars to keep the payload small and the chart fast to draw --
        plenty for visual pattern context without shipping the whole
        history over the wire.
        """
        tail = df.tail(max_bars)
        out = []
        for idx, row in tail.iterrows():
            out.append({
                "time": idx.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
            })
        return out

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

    # ---- Phase 1 additions: EMA/SMA/ATR/Bollinger/OBV/VWAP ----
    # All deterministic price-action math on the same real df already
    # fetched above -- same "no AI guessing involved" principle as the
    # existing RSI/MACD/swing-point methods.

    @staticmethod
    def _ema(closes: pd.Series, span: int) -> pd.Series:
        return closes.ewm(span=span, adjust=False).mean()

    @staticmethod
    def _sma(closes: pd.Series, window: int) -> pd.Series:
        return closes.rolling(min(window, len(closes))).mean()

    @staticmethod
    def _atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14) -> pd.Series:
        """
        Average True Range -- standard volatility measure, used below both
        as an extra confluence signal and (more importantly) to size real
        stop-loss/take-profit distances in _decision_levels() instead of
        picking an arbitrary %.
        """
        prev_close = closes.shift(1)
        tr = pd.concat([
            highs - lows,
            (highs - prev_close).abs(),
            (lows - prev_close).abs(),
        ], axis=1).max(axis=1)
        return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    @staticmethod
    def _bollinger(closes: pd.Series, period: int = 20, num_std: float = 2.0):
        mid = closes.rolling(min(period, len(closes))).mean()
        std = closes.rolling(min(period, len(closes))).std()
        upper = mid + num_std * std
        lower = mid - num_std * std
        return upper, mid, lower

    @staticmethod
    def _obv(closes: pd.Series, volume: pd.Series) -> pd.Series:
        direction = np.sign(closes.diff().fillna(0))
        return (direction * volume).cumsum()

    @staticmethod
    def _vwap(highs: pd.Series, lows: pd.Series, closes: pd.Series, volume: pd.Series) -> pd.Series:
        typical_price = (highs + lows + closes) / 3
        cum_vol = volume.cumsum().replace(0, np.nan)
        return (typical_price * volume).cumsum() / cum_vol

    # ---- Step 2 (2026-07-18) Signal Engine upgrade additions ----
    # SuperTrend / Ichimoku / Donchian / Keltner -- all computed purely
    # from bar i and bar i-1 (or a trailing rolling window ending at bar
    # i), same no-look-ahead convention as every other indicator in this
    # class, so BacktestService can reuse these directly if a future
    # strategy family wants them without any extra scrutiny.

    @staticmethod
    def _supertrend(highs: pd.Series, lows: pd.Series, closes: pd.Series,
                     period: int = 10, multiplier: float = 3.0):
        """
        Standard SuperTrend: an ATR-based trailing stop/trend line that
        flips side when price closes through it. Returns (line, direction)
        where direction is +1 (bullish -- line acts as support below
        price) or -1 (bearish -- line acts as resistance above price).
        Implemented as an explicit bar-by-bar loop (like _swing_points())
        because each bar's "final" band depends on the PRIOR bar's final
        band, not just a rolling window -- that recursive definition is
        the actual SuperTrend algorithm, not a look-ahead shortcut.
        """
        atr = TechnicalAnalysisService._atr(highs, lows, closes, period)
        hl2 = (highs + lows) / 2
        basic_upper = (hl2 + multiplier * atr).values
        basic_lower = (hl2 - multiplier * atr).values
        closes_v = closes.values
        n = len(closes_v)

        final_upper = np.zeros(n)
        final_lower = np.zeros(n)
        st = np.zeros(n)
        direction = np.ones(n, dtype=int) * -1

        for i in range(n):
            if i == 0 or np.isnan(basic_upper[i]) or np.isnan(basic_lower[i]):
                final_upper[i] = 0.0 if np.isnan(basic_upper[i]) else basic_upper[i]
                final_lower[i] = 0.0 if np.isnan(basic_lower[i]) else basic_lower[i]
                st[i] = final_upper[i]
                direction[i] = -1
                continue

            final_upper[i] = (
                basic_upper[i]
                if (basic_upper[i] < final_upper[i - 1] or closes_v[i - 1] > final_upper[i - 1])
                else final_upper[i - 1]
            )
            final_lower[i] = (
                basic_lower[i]
                if (basic_lower[i] > final_lower[i - 1] or closes_v[i - 1] < final_lower[i - 1])
                else final_lower[i - 1]
            )

            if st[i - 1] == final_upper[i - 1] and closes_v[i] <= final_upper[i]:
                st[i], direction[i] = final_upper[i], -1
            elif st[i - 1] == final_upper[i - 1] and closes_v[i] > final_upper[i]:
                st[i], direction[i] = final_lower[i], 1
            elif st[i - 1] == final_lower[i - 1] and closes_v[i] >= final_lower[i]:
                st[i], direction[i] = final_lower[i], 1
            elif st[i - 1] == final_lower[i - 1] and closes_v[i] < final_lower[i]:
                st[i], direction[i] = final_upper[i], -1
            else:
                st[i], direction[i] = final_upper[i], -1

        return pd.Series(st, index=closes.index), pd.Series(direction, index=closes.index)

    @staticmethod
    def _ichimoku(highs: pd.Series, lows: pd.Series, closes: pd.Series,
                  tenkan_period: int = 9, kijun_period: int = 26, senkou_b_period: int = 52):
        """
        Ichimoku Kinko Hyo's Tenkan-sen / Kijun-sen / Senkou Span A & B.
        Deliberately NOT shifted 26 bars forward the way a chart normally
        PLOTS the cloud -- that shift is a display convention (drawing
        today's cloud ahead of today's candle), not a data dependency, and
        shifting it here would make "today's cloud" secretly describe a
        future bar. Used as a same-bar "is price above/below/inside the
        cloud computed from data up to and including today" signal, which
        stays fully causal.
        """
        tenkan = (highs.rolling(min(tenkan_period, len(highs))).max()
                  + lows.rolling(min(tenkan_period, len(lows))).min()) / 2
        kijun = (highs.rolling(min(kijun_period, len(highs))).max()
                 + lows.rolling(min(kijun_period, len(lows))).min()) / 2
        senkou_a = (tenkan + kijun) / 2
        senkou_b = (highs.rolling(min(senkou_b_period, len(highs))).max()
                    + lows.rolling(min(senkou_b_period, len(lows))).min()) / 2
        return tenkan, kijun, senkou_a, senkou_b

    @staticmethod
    def _donchian(highs: pd.Series, lows: pd.Series, period: int = 20):
        """Donchian Channel: rolling `period`-bar high/low envelope."""
        upper = highs.rolling(min(period, len(highs))).max()
        lower = lows.rolling(min(period, len(lows))).min()
        return upper, lower

    @staticmethod
    def _keltner(closes: pd.Series, highs: pd.Series, lows: pd.Series,
                 period: int = 20, multiplier: float = 2.0):
        """
        Keltner Channel: EMA basis +/- ATR*multiplier. Unlike Bollinger
        (std-dev based, read here as mean-reversion overbought/oversold),
        Keltner is read as a trend-continuation signal below -- a close
        beyond the band on an ATR-scaled channel is treated in this
        codebase's confluence scoring as confirming a strong directional
        move, not as "overextended".
        """
        ema = closes.ewm(span=period, adjust=False).mean()
        atr = TechnicalAnalysisService._atr(highs, lows, closes, period)
        upper = ema + multiplier * atr
        lower = ema - multiplier * atr
        return upper, ema, lower

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


    # Phase 1 Confluence Engine upgrade: each signal type now carries a
    # weight instead of counting equally. Weights reflect how much a signal
    # type is generally trusted in price-action analysis (proximity to a
    # real support/resistance zone is weighted higher than a single
    # oscillator reading, for example). Output shape (score/direction/
    # confidence/confidence_pct/signals_counted/bullish_signals/
    # bearish_signals) is unchanged so every existing consumer keeps
    # working -- only the math behind `score`/`confidence_pct` changed.
    _CONFLUENCE_WEIGHTS = {
        "trend": 1.2,
        "rsi": 1.0,
        "macd": 1.0,
        "support": 1.3,
        "resistance": 1.3,
        "fib": 0.8,
        "bollinger": 0.9,
        "obv": 0.9,
        # Step 2 (2026-07-18) Signal Engine upgrade additions. SuperTrend
        # weighted close to trend (same trend-following family); Donchian
        # weighted like a breakout-confirmation signal (comparable to
        # support/resistance proximity, slightly lower since it doesn't
        # cluster multiple touches); Ichimoku and Keltner weighted like
        # the other single-oscillator-style signals.
        "supertrend": 1.1,
        "donchian": 1.0,
        "ichimoku": 1.0,
        "keltner": 0.8,
    }

    @classmethod
    def _confluence(
        cls,
        trend: str,
        rsi: Optional[float],
        macd_hist: float,
        last_close: float,
        support: Optional[Dict],
        resistance: Optional[Dict],
        fib: Optional[Dict],
        bollinger: Optional[Dict] = None,
        obv_trend: Optional[str] = None,
        supertrend: Optional[Dict] = None,
        ichimoku: Optional[Dict] = None,
        donchian: Optional[Dict] = None,
        keltner: Optional[Dict] = None,
        proximity_tolerance: float = 0.03,
    ) -> Dict:
        """
        Confluence scoring — cross-checks the independent numeric signals
        against each other instead of reporting them as an unrelated list.
        This is what "AI Chart Intelligence Core" calls a Confluence Engine:
        the more independent signals agree (weighted by how much each
        signal type is generally trusted), the higher the confidence.

        Each signal contributes +weight (bullish), -weight (bearish) or is
        skipped (neutral/not available). The final score is the net
        weighted bias as a % of total weight counted, so it's comparable
        across tickers with different numbers of available signals.
        """
        w = cls._CONFLUENCE_WEIGHTS
        signals: List[Dict] = []

        # 1. Trend (price vs MA50)
        if trend == "上升":
            signals.append({"signal": "趨勢（高於MA50）", "bias": 1, "weight": w["trend"]})
        elif trend == "下降":
            signals.append({"signal": "趨勢（低於MA50）", "bias": -1, "weight": w["trend"]})

        # 2. RSI
        if rsi is not None:
            if rsi >= 70:
                signals.append({"signal": f"RSI過熱（{rsi}，≥70）", "bias": -1, "weight": w["rsi"]})
            elif rsi <= 30:
                signals.append({"signal": f"RSI超賣（{rsi}，≤30）", "bias": 1, "weight": w["rsi"]})
            elif rsi > 50:
                signals.append({"signal": f"RSI偏多（{rsi}，>50）", "bias": 1, "weight": w["rsi"]})
            else:
                signals.append({"signal": f"RSI偏空（{rsi}，<50）", "bias": -1, "weight": w["rsi"]})

        # 3. MACD histogram
        if macd_hist > 0:
            signals.append({"signal": "MACD柱狀圖轉正（金叉）", "bias": 1, "weight": w["macd"]})
        else:
            signals.append({"signal": "MACD柱狀圖轉負（死叉）", "bias": -1, "weight": w["macd"]})

        # 4. Proximity to support/resistance
        if support and last_close > 0:
            dist = abs(last_close - support["level"]) / last_close
            if dist <= proximity_tolerance:
                signals.append({"signal": "現價貼近支撐位，反彈機會", "bias": 1, "weight": w["support"]})
        if resistance and last_close > 0:
            dist = abs(resistance["level"] - last_close) / last_close
            if dist <= proximity_tolerance:
                signals.append({"signal": "現價貼近阻力位，回落風險", "bias": -1, "weight": w["resistance"]})

        # 5. Position relative to 0.618 Fibonacci retracement
        if fib:
            if last_close >= fib["level_0618"]:
                signals.append({"signal": "現價企穩0.618回調位之上", "bias": 1, "weight": w["fib"]})
            else:
                signals.append({"signal": "現價跌穿0.618回調位，結構轉弱", "bias": -1, "weight": w["fib"]})

        # 6. Bollinger Band position (Phase 1 addition)
        if bollinger:
            if last_close >= bollinger["upper"]:
                signals.append({"signal": "現價觸及布林上軌，超買風險", "bias": -1, "weight": w["bollinger"]})
            elif last_close <= bollinger["lower"]:
                signals.append({"signal": "現價觸及布林下軌，超賣反彈機會", "bias": 1, "weight": w["bollinger"]})

        # 7. OBV (on-balance volume) trend confirmation (Phase 1 addition)
        if obv_trend == "上升":
            signals.append({"signal": "OBV成交量動能上升，資金流入", "bias": 1, "weight": w["obv"]})
        elif obv_trend == "下降":
            signals.append({"signal": "OBV成交量動能下降，資金流出", "bias": -1, "weight": w["obv"]})

        # 8. SuperTrend direction (Step 2 addition)
        if supertrend:
            if supertrend["direction"] == "上升":
                signals.append({"signal": "SuperTrend看多（收於支撐線之上）", "bias": 1, "weight": w["supertrend"]})
            else:
                signals.append({"signal": "SuperTrend看空（收於阻力線之下）", "bias": -1, "weight": w["supertrend"]})

        # 9. Ichimoku Cloud position (Step 2 addition)
        if ichimoku:
            if ichimoku["cloud_position"].startswith("雲上"):
                signals.append({"signal": "現價企穩Ichimoku雲之上，結構偏多", "bias": 1, "weight": w["ichimoku"]})
            elif ichimoku["cloud_position"].startswith("雲下"):
                signals.append({"signal": "現價跌穿Ichimoku雲之下，結構偏空", "bias": -1, "weight": w["ichimoku"]})
            # 雲內 (inside the cloud) is genuinely neutral -- skipped, not
            # forced into a bullish/bearish bucket.

        # 10. Donchian Channel breakout (Step 2 addition)
        if donchian:
            if last_close >= donchian["upper"]:
                signals.append({"signal": "現價創20日新高，Donchian突破訊號", "bias": 1, "weight": w["donchian"]})
            elif last_close <= donchian["lower"]:
                signals.append({"signal": "現價創20日新低，Donchian破位訊號", "bias": -1, "weight": w["donchian"]})

        # 11. Keltner Channel (Step 2 addition) -- read as trend
        # continuation (see _keltner()'s docstring), the opposite framing
        # from Bollinger's mean-reversion read above.
        if keltner:
            if last_close >= keltner["upper"]:
                signals.append({"signal": "現價突破Keltner上軌，強勢延續", "bias": 1, "weight": w["keltner"]})
            elif last_close <= keltner["lower"]:
                signals.append({"signal": "現價跌穿Keltner下軌，弱勢延續", "bias": -1, "weight": w["keltner"]})

        counted = len(signals)
        weight_total = sum(s["weight"] for s in signals)
        net_weighted = sum(s["bias"] * s["weight"] for s in signals)
        score = round((net_weighted / weight_total) * 100, 1) if weight_total else 0.0

        if counted == 0:
            direction, confidence = "數據不足", "低"
        elif score >= 20:
            direction = "偏多"
        elif score <= -20:
            direction = "偏空"
        else:
            direction = "訊號分歧，中性"

        agree_ratio = abs(net_weighted) / weight_total if weight_total else 0
        if counted == 0:
            confidence = "低"
        elif agree_ratio >= 0.6:
            confidence = "高"
        elif agree_ratio >= 0.3:
            confidence = "中"
        else:
            confidence = "低"

        return {
            "score": score,  # -100 (全部偏空) 至 +100 (全部偏多)
            "direction": direction,
            "confidence": confidence,
            # Real numeric version of `confidence` (agree_ratio as a %),
            # added for surfaces that want a number rather than a
            # 高/中/低 label (e.g. the homepage Hero's live result card).
            # Same underlying real signal-agreement math, just not bucketed.
            "confidence_pct": round(agree_ratio * 100, 1),
            "signals_counted": counted,
            "bullish_signals": [s["signal"] for s in signals if s["bias"] > 0],
            "bearish_signals": [s["signal"] for s in signals if s["bias"] < 0],
        }

    @staticmethod
    def _decision_levels(
        direction: str,
        last_close: float,
        support: Optional[Dict],
        resistance: Optional[Dict],
        atr14: Optional[float],
    ) -> Optional[Dict]:
        """
        Phase 1 Decision Engine upgrade: real Entry/Stop-Loss/Take-Profit/
        Risk-Reward levels derived from actual support/resistance/ATR,
        instead of a plain "Bullish/Bearish" label. Deliberately returns
        None (rendered as nothing, not a fabricated number) when:
          - the Confluence Engine itself has no clear directional bias
            ("訊號分歧，中性" / "數據不足"), or
          - there isn't a real structural level OR ATR to anchor a stop on.

        Absolute position sizing (e.g. "buy 40 shares") is intentionally
        NOT computed here — that needs the user's account size/risk
        tolerance, which this service has no access to, and guessing one
        would violate this codebase's no-fabrication rule. Risk% (distance
        to stop as a % of entry) is included instead, since that's fully
        derivable from real price data alone.
        """
        if direction not in ("偏多", "偏空"):
            return None

        entry = last_close
        atr_buffer = atr14 * 1.5 if atr14 else None

        if direction == "偏多":  # long bias
            stop = support["level"] if support else (entry - atr_buffer if atr_buffer else None)
            if stop is None or stop >= entry:
                return None
            risk = entry - stop
            tp1 = resistance["level"] if resistance and resistance["level"] > entry else entry + risk
            tp2 = entry + risk * 2
            tp3 = entry + risk * 3
            bias_label = "long"
        else:  # short bias
            stop = resistance["level"] if resistance else (entry + atr_buffer if atr_buffer else None)
            if stop is None or stop <= entry:
                return None
            risk = stop - entry
            tp1 = support["level"] if support and support["level"] < entry else entry - risk
            tp2 = entry - risk * 2
            tp3 = entry - risk * 3
            bias_label = "short"

        if risk <= 0:
            return None

        reward1 = abs(tp1 - entry)
        return {
            "bias": bias_label,
            "entry": round(entry, 2),
            "stop_loss": round(stop, 2),
            "take_profits": [round(tp1, 2), round(tp2, 2), round(tp3, 2)],
            "risk_reward": round(reward1 / risk, 2),
            "risk_pct": round(risk / entry * 100, 2),
        }

    @staticmethod
    def _market_structure(
        closes: pd.Series,
        highs: pd.Series,
        lows: pd.Series,
        swing_highs: List[float],
        swing_lows: List[float],
    ) -> Optional[Dict]:
        """
        Phase 2 Market Structure Engine -- BOS (Break of Structure), CHOCH
        (Change of Character) and liquidity sweeps, all deterministic
        price-action rules on the SAME chronologically-ordered swing
        points already computed above (no new data fetch, no AI
        guessing).

        Definitions used here:
          - "prior structure" is read off the last two swing highs/lows:
            higher-high + higher-low = uptrend, lower-high + lower-low =
            downtrend, anything else = mixed/consolidation.
          - BOS: latest close breaks past the most recent swing level in
            the SAME direction as prior structure -- confirms continuation.
          - CHOCH: latest close breaks past the most recent swing level
            AGAINST prior structure -- an early sign structure may be
            changing (not a confirmed reversal, just the first character
            change).
          - Liquidity sweep: the latest bar's high/low pokes past a swing
            level (a classic "stop hunt" wick) but the CLOSE comes back
            inside -- price rejected the level rather than confirming
            through it.

        Returns None (not fabricated events) when there are fewer than 2
        swing highs/lows to compare -- not enough structure to classify.
        """
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return None

        last_close = float(closes.iloc[-1])
        last_high = float(highs.iloc[-1])
        last_low = float(lows.iloc[-1])

        recent_high, prior_high = swing_highs[-1], swing_highs[-2]
        recent_low, prior_low = swing_lows[-1], swing_lows[-2]

        if recent_high > prior_high and recent_low > prior_low:
            prior_structure = "uptrend"
        elif recent_high < prior_high and recent_low < prior_low:
            prior_structure = "downtrend"
        else:
            prior_structure = "mixed"

        events: List[Dict] = []

        if prior_structure == "uptrend" and last_close > recent_high:
            events.append({
                "type": "BOS", "direction": "bullish",
                "detail": f"價格企穩突破前高 {round(recent_high, 2)}，確認上升結構延續",
            })
        elif prior_structure == "downtrend" and last_close < recent_low:
            events.append({
                "type": "BOS", "direction": "bearish",
                "detail": f"價格企穩跌穿前低 {round(recent_low, 2)}，確認下降結構延續",
            })

        if prior_structure == "downtrend" and last_close > recent_high:
            events.append({
                "type": "CHOCH", "direction": "bullish",
                "detail": f"價格突破前高 {round(recent_high, 2)}，下降結構出現轉勢跡象",
            })
        elif prior_structure == "uptrend" and last_close < recent_low:
            events.append({
                "type": "CHOCH", "direction": "bearish",
                "detail": f"價格跌穿前低 {round(recent_low, 2)}，上升結構出現轉勢跡象",
            })

        if last_high > recent_high and last_close < recent_high:
            events.append({
                "type": "liquidity_sweep", "direction": "bearish",
                "detail": f"高位插針掃過前高 {round(recent_high, 2)} 後收返落嚟，疑似掃流動性",
            })
        if last_low < recent_low and last_close > recent_low:
            events.append({
                "type": "liquidity_sweep", "direction": "bullish",
                "detail": f"低位插針穿過前低 {round(recent_low, 2)} 後收返上去，疑似掃流動性",
            })

        return {
            "prior_structure": prior_structure,
            "recent_swing_high": round(recent_high, 2),
            "recent_swing_low": round(recent_low, 2),
            "events": events,
        }


technical_service = TechnicalAnalysisService()


# ---- Phase 2 Multi-Timeframe Engine ----
# Compares trend/confluence direction across the timeframes the underlying
# data sources actually support natively -- Weekly, Daily, 1-Hour. No fake
# "4H" bucket: yfinance/Alpaca don't offer a native 4-hour bar, and
# resampling 1H bars into synthetic 4H candles here would be presenting
# derived data as if it were a real timeframe, which this codebase avoids.
MULTI_TIMEFRAMES = [
    {"label": "Weekly", "key": "weekly", "period": "2y", "interval": "1wk"},
    {"label": "Daily", "key": "daily", "period": "6mo", "interval": "1d"},
    {"label": "1-Hour", "key": "1h", "period": "5d", "interval": "1h"},
]


def get_multi_timeframe_analysis(symbol: str) -> Optional[Dict]:
    """
    Fetches the SAME real get_technical_analysis() output at 3 different
    timeframes and summarises whether they agree. Deliberately a separate,
    lazily-called function (see api/chart_analysis.py's dedicated
    endpoint) rather than bundled into every search, since it triples the
    number of historical-data calls per request.
    """
    results = []
    for tf in MULTI_TIMEFRAMES:
        r = get_technical_analysis(symbol, period=tf["period"], interval=tf["interval"])
        if r and "error" not in r:
            results.append({
                "label": tf["label"],
                "key": tf["key"],
                "trend": r["trend"],
                "confluence_direction": r["confluence"]["direction"],
                "confluence_score": r["confluence"]["score"],
            })

    if not results:
        return None

    bullish = sum(1 for r in results if r["confluence_direction"] == "偏多")
    bearish = sum(1 for r in results if r["confluence_direction"] == "偏空")

    if bullish == len(results):
        alignment = "全部時間框架一致偏多"
    elif bearish == len(results):
        alignment = "全部時間框架一致偏空"
    elif bullish > bearish:
        alignment = "多數時間框架偏多，但有分歧"
    elif bearish > bullish:
        alignment = "多數時間框架偏空，但有分歧"
    else:
        alignment = "時間框架訊號分歧，中性"

    return {"timeframes": results, "alignment": alignment}


def get_technical_analysis(
    symbol: str, period: str = "6mo", interval: str = "1d"
) -> Dict:
    return technical_service.get_analysis(symbol, period, interval)


def fetch_ohlc_history(symbol: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """
    Public wrapper around TechnicalAnalysisService._fetch_history() --
    2026-07-18 data-compliance pass: several other files (services/
    anomaly_history_service.py, services/trending_stocks_service.py,
    api/pipeline_api.py) previously called `yfinance` directly for plain
    OHLC history, bypassing the Alpaca-first/yfinance-fallback routing
    this class already has (Alpaca's terms explicitly permit displaying
    data to end users commercially; yfinance's do not -- see
    services/license_registry.py). Routing them through this shared
    function means every plain-OHLC-history caller in the codebase now
    gets the same reduced yfinance exposure for free, instead of each
    file needing its own copy of the Alpaca-routing logic.

    Not a fit for every yfinance use in this codebase: `yf.Ticker(...).
    info`/`.fast_info` (services/market_data_service.py, api/admin.py)
    and `yf.Lookup(...)` (services/ticker_search_service.py) are
    different yfinance features -- quote/company-info snapshots and
    fuzzy ticker search -- that Alpaca's free IEX bars endpoint doesn't
    replace one-for-one. Migrating those needs a genuinely different
    integration (Alpaca's separate quote-snapshot API), tracked as
    follow-up work rather than silently left half-done here.
    """
    return TechnicalAnalysisService._fetch_history(symbol, period, interval)


if __name__ == "__main__":
    import json

    print(json.dumps(get_technical_analysis("AAPL"), indent=2, ensure_ascii=False))
