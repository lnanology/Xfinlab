"""
Backtest Service -- Step 3 of the Strategy Intelligence roadmap
(2026-07-18).

This is the FIRST real backtesting infrastructure anywhere in this
codebase. Two placeholder files already existed under this name
(backend/trading/backtest_engine.py and backend/evolution/backtest_
engine.py) -- both are stubs; the evolution one literally returns
`random.uniform(-1, 1) * weight` (see api/pipeline_api.py's own comment
on this). Neither is touched here; this module is the real one and
nothing else should import those two.

What this does: fetches real historical OHLC via TechnicalAnalysis
Service's existing data pipeline (Alpaca-first, yfinance fallback --
same source as every other real-data feature) and simulates each
strategy's entry rule bar-by-bar, then reports honest win rate / average
return / max drawdown / profit factor / a trade-level Sharpe-like ratio.

No look-ahead bias by construction: every indicator used here (SMA, RSI,
MACD, Bollinger, OBV, ATR, Donchian) is computed with pandas .rolling()/
.ewm()/.diff()/.shift(1), all of which only ever look backward from each
bar. This deliberately excludes TechnicalAnalysisService's fractal swing-
point-based support/resistance signal (used in the live Confluence
Engine and Decision Levels) because that detector needs `window` FUTURE
bars on each side to confirm a swing point exists -- using it here would
silently leak future information into a "historical" entry decision and
produce a fake win rate. This is a known, stated scope limitation, not a
silent omission.

Every result also carries an explicit `caveats` list (no fees/slippage
modeled, small sample sizes are not statistically reliable, past
performance is not predictive) -- this codebase's established principle
of never presenting a number as more authoritative than it actually is.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from services.technical_analysis_service import TechnicalAnalysisService

logger = logging.getLogger(__name__)

_svc = TechnicalAnalysisService

WARMUP_BARS = 60      # bars to skip at the start so SMA50/Bollinger/Donchian/OBV windows are already full
MAX_HOLD_BARS = 20    # force-exit at close if neither stop nor target hit within this many bars
ATR_STOP_MULT = 1.5   # same stop-distance convention as _decision_levels()'s ATR fallback branch
ATR_TARGET_MULT = 3.0  # ~1:2 risk-reward target, deliberately conservative vs the live 1:3 TP1


class BacktestService:

    STRATEGIES = ["confluence_trend", "breakout_donchian", "mean_reversion_bollinger"]

    # ---- public entry points ----

    @classmethod
    def run(cls, symbol: str, strategy: str = "confluence_trend",
            period: str = "2y", interval: str = "1d") -> Dict:
        if strategy not in cls.STRATEGIES:
            return {"error": f"未知策略：{strategy}，可用：{', '.join(cls.STRATEGIES)}"}

        try:
            df = _svc._fetch_history(symbol, period, interval)
        except Exception as e:
            return {"error": f"攞唔到 {symbol} 嘅歷史數據：{str(e)}"}

        if df is None or df.empty or len(df) < WARMUP_BARS + 10:
            return {"error": f"{symbol} 歷史數據不足，無法回測（需要至少 {WARMUP_BARS + 10} 條K線）"}

        df = df.dropna()
        closes, highs, lows, volume = df["Close"], df["High"], df["Low"], df["Volume"]

        ind = cls._compute_causal_indicators(closes, highs, lows, volume)
        signal_fn = {
            "confluence_trend": cls._signal_confluence_trend,
            "breakout_donchian": cls._signal_breakout_donchian,
            "mean_reversion_bollinger": cls._signal_mean_reversion_bollinger,
        }[strategy]

        trades = cls._simulate(df, ind, signal_fn)
        stats = cls._compute_stats(trades)

        return {
            "symbol": symbol.upper(),
            "strategy": strategy,
            "period": period,
            "interval": interval,
            "data_points": len(df),
            "trades": trades,
            "stats": stats,
            "caveats": [
                "未計入手續費/滑點，實際表現會較差。",
                "支撐/阻力型訊號（依賴未來K棒確認嘅fractal swing point）刻意冇加入呢個回測，避免未來數據滲入歷史判斷。",
                "細樣本（交易次數少）嘅勝率統計學上唔可靠，請留意 stats.trade_count。",
                "過去表現不代表未來結果，呢個唔係投資建議。",
            ],
        }

    @classmethod
    def compare(cls, symbol: str, period: str = "2y", interval: str = "1d") -> Dict:
        """
        Runs every registered strategy for the same symbol/period and
        sorts by win rate (sharpe_like as tiebreaker) -- purely an
        informational ranking, same "probability framing, not a BUY/SELL
        recommendation" caution as api/pipeline_api.py already applies
        elsewhere.
        """
        results = []
        for strat in cls.STRATEGIES:
            r = cls.run(symbol, strategy=strat, period=period, interval=interval)
            if "error" not in r:
                results.append(r)
        if not results:
            return {"error": f"{symbol.upper()} 無法完成任何策略回測（歷史數據不足或攞唔到）"}

        def sort_key(r):
            s = r["stats"]
            wr = s.get("win_rate_pct")
            sh = s.get("sharpe_like")
            return (wr if wr is not None else -1, sh if sh is not None else -999)

        results.sort(key=sort_key, reverse=True)
        return {
            "symbol": symbol.upper(),
            "period": period,
            "strategies": results,
            "disclaimer": "以上排名純粹基於歷史回測勝率排序，並非投資建議，亦不保證未來表現。",
        }

    # ---- causal indicator computation (whole-series, still no look-ahead) ----

    @staticmethod
    def _compute_causal_indicators(closes: pd.Series, highs: pd.Series,
                                    lows: pd.Series, volume: pd.Series) -> Dict:
        n = len(closes)
        sma50 = closes.rolling(min(50, n)).mean()
        trend = np.where(closes.values > sma50.values, 1, -1)

        rsi = _svc._rsi(closes)
        _, _, macd_hist = _svc._macd(closes)
        bb_upper, bb_mid, bb_lower = _svc._bollinger(closes, 20, 2)
        atr14 = _svc._atr(highs, lows, closes, 14)

        obv = _svc._obv(closes, volume)
        obv_window = 10
        obv_vals = obv.values
        obv_trend = [0] * n
        for i in range(obv_window, n):
            obv_trend[i] = 1 if obv_vals[i] > obv_vals[i - obv_window] else -1

        # Donchian Channel(20), shifted 1 bar so "today's" breakout check
        # compares against the PRIOR 20 bars, never including today itself.
        donchian_high = highs.rolling(20).max().shift(1)
        donchian_low = lows.rolling(20).min().shift(1)

        return {
            "close": closes.values,
            "trend": trend,
            "rsi": rsi.values,
            "macd_hist": macd_hist.values,
            "bb_upper": bb_upper.values,
            "bb_lower": bb_lower.values,
            "atr14": atr14.values,
            "obv_trend": obv_trend,
            "donchian_high": donchian_high.values,
            "donchian_low": donchian_low.values,
        }

    # ---- strategy signal functions (all read only ind[...][i], i.e. only
    # data available AT bar i) ----

    @staticmethod
    def _signal_confluence_trend(i: int, ind: Dict) -> Optional[str]:
        """
        Simplified version of TechnicalAnalysisService._confluence() --
        same weights, minus the support/resistance/Fibonacci signals
        (which need look-ahead-tainted swing points, see module docstring).
        """
        w = _svc._CONFLUENCE_WEIGHTS
        signals: List[tuple] = []

        if ind["trend"][i] == 1:
            signals.append((1, w["trend"]))
        elif ind["trend"][i] == -1:
            signals.append((-1, w["trend"]))

        rsi = ind["rsi"][i]
        if rsi is not None and not np.isnan(rsi):
            if rsi >= 70:
                signals.append((-1, w["rsi"]))
            elif rsi <= 30:
                signals.append((1, w["rsi"]))
            elif rsi > 50:
                signals.append((1, w["rsi"]))
            else:
                signals.append((-1, w["rsi"]))

        macd_hist = ind["macd_hist"][i]
        if macd_hist is not None and not np.isnan(macd_hist):
            signals.append((1 if macd_hist > 0 else -1, w["macd"]))

        close = ind["close"][i]
        bb_upper, bb_lower = ind["bb_upper"][i], ind["bb_lower"][i]
        if bb_upper is not None and not np.isnan(bb_upper):
            if close >= bb_upper:
                signals.append((-1, w["bollinger"]))
            elif close <= bb_lower:
                signals.append((1, w["bollinger"]))

        obv_trend = ind["obv_trend"][i]
        if obv_trend == 1:
            signals.append((1, w["obv"]))
        elif obv_trend == -1:
            signals.append((-1, w["obv"]))

        if not signals:
            return None
        weight_total = sum(wt for _, wt in signals)
        net = sum(bias * wt for bias, wt in signals)
        score = (net / weight_total) * 100 if weight_total else 0.0

        if score >= 20:
            return "long"
        if score <= -20:
            return "short"
        return None

    @staticmethod
    def _signal_breakout_donchian(i: int, ind: Dict) -> Optional[str]:
        close = ind["close"][i]
        dh, dl = ind["donchian_high"][i], ind["donchian_low"][i]
        if dh is None or np.isnan(dh) or dl is None or np.isnan(dl):
            return None
        if close > dh:
            return "long"
        if close < dl:
            return "short"
        return None

    @staticmethod
    def _signal_mean_reversion_bollinger(i: int, ind: Dict) -> Optional[str]:
        close = ind["close"][i]
        bb_upper, bb_lower = ind["bb_upper"][i], ind["bb_lower"][i]
        if bb_upper is None or np.isnan(bb_upper):
            return None
        if close <= bb_lower:
            return "long"
        if close >= bb_upper:
            return "short"
        return None

    # ---- simulation loop ----

    @staticmethod
    def _simulate(df: pd.DataFrame, ind: Dict, signal_fn) -> List[Dict]:
        opens = df["Open"].values
        highs = df["High"].values
        lows = df["Low"].values
        closes = df["Close"].values
        n = len(df)
        trades: List[Dict] = []

        i = WARMUP_BARS
        while i < n - 1:
            sig = signal_fn(i, ind)
            if sig not in ("long", "short"):
                i += 1
                continue

            entry_idx = i + 1  # enter at NEXT bar's open -- the signal at
            # bar i is only known once bar i has closed, so acting on it
            # at bar i's own close/price would itself be a subtle look-
            # ahead. Entering at i+1's open is the standard, honest fix.
            if entry_idx >= n:
                break

            entry_price = float(opens[entry_idx])
            atr = ind["atr14"][entry_idx]
            if atr is None or np.isnan(atr) or atr <= 0:
                i += 1
                continue
            atr = float(atr)  # cast off numpy scalar so stop/target/ret_pct
            # below stay native Python floats all the way through --
            # otherwise numpy float64 leaks into the JSON API response.

            if sig == "long":
                stop = entry_price - atr * ATR_STOP_MULT
                target = entry_price + atr * ATR_TARGET_MULT
            else:
                stop = entry_price + atr * ATR_STOP_MULT
                target = entry_price - atr * ATR_TARGET_MULT

            exit_idx, exit_price, exit_reason = None, None, None
            for j in range(entry_idx, min(entry_idx + MAX_HOLD_BARS, n)):
                h, l = highs[j], lows[j]
                if sig == "long":
                    if l <= stop:
                        exit_idx, exit_price, exit_reason = j, stop, "stop"
                        break
                    if h >= target:
                        exit_idx, exit_price, exit_reason = j, target, "target"
                        break
                else:
                    if h >= stop:
                        exit_idx, exit_price, exit_reason = j, stop, "stop"
                        break
                    if l <= target:
                        exit_idx, exit_price, exit_reason = j, target, "target"
                        break

            if exit_idx is None:
                exit_idx = min(entry_idx + MAX_HOLD_BARS - 1, n - 1)
                exit_price = float(closes[exit_idx])
                exit_reason = "timeout"

            ret_pct = (
                (exit_price - entry_price) / entry_price * 100
                if sig == "long"
                else (entry_price - exit_price) / entry_price * 100
            )

            trades.append({
                "direction": sig,
                "entry_date": str(df.index[entry_idx].date()),
                "exit_date": str(df.index[exit_idx].date()),
                "entry_price": round(entry_price, 2),
                "exit_price": round(float(exit_price), 2),
                "return_pct": round(ret_pct, 2),
                "exit_reason": exit_reason,
                "bars_held": exit_idx - entry_idx,
            })

            i = exit_idx + 1  # no overlapping trades -- resume scanning after this one closes

        return trades

    # ---- stats ----

    @staticmethod
    def _compute_stats(trades: List[Dict]) -> Dict:
        n = len(trades)
        if n == 0:
            return {
                "trade_count": 0,
                "win_rate_pct": None,
                "avg_return_pct": None,
                "max_drawdown_pct": None,
                "profit_factor": None,
                "sharpe_like": None,
                "note": "回測期間冇觸發任何交易訊號，無法計算統計數字。",
            }

        returns = [t["return_pct"] for t in trades]
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]

        win_rate = round(len(wins) / n * 100, 1)
        avg_return = round(sum(returns) / n, 2)

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        if gross_loss > 0:
            profit_factor = round(gross_profit / gross_loss, 2)
        elif gross_profit > 0:
            profit_factor = None  # no losing trades at all -- ratio is undefined, not "infinite alpha"
        else:
            profit_factor = None

        # Simplified equity curve: each trade risks the whole position,
        # sequential (no overlapping trades, no compounding-vs-position-
        # sizing complexity modeled) -- good enough for a directional max
        # drawdown read, not a real portfolio simulation.
        equity = [1.0]
        for r in returns:
            equity.append(equity[-1] * (1 + r / 100))
        peak = equity[0]
        max_dd = 0.0
        for v in equity:
            peak = max(peak, v)
            dd = (peak - v) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)

        mean_r = sum(returns) / n
        var_r = sum((r - mean_r) ** 2 for r in returns) / n if n > 1 else 0
        std_r = var_r ** 0.5
        sharpe_like = round(mean_r / std_r, 2) if std_r > 0 else None

        return {
            "trade_count": n,
            "win_rate_pct": float(win_rate),
            "avg_return_pct": float(avg_return),
            "max_drawdown_pct": float(round(max_dd, 2)),
            "profit_factor": float(profit_factor) if profit_factor is not None else None,
            # Per-trade return / per-trade stdev -- NOT an annualized
            # Sharpe ratio (that needs daily account-level returns, which
            # this one-trade-at-a-time simulation doesn't produce).
            # Deliberately labeled "sharpe_like" so it's never mistaken
            # for the real, more rigorous metric.
            "sharpe_like": float(sharpe_like) if sharpe_like is not None else None,
        }
