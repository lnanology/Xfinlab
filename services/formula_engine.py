"""
Formula Engine (task #772, AJ: "先建個engine 有全球所有 POWERFUL FORMULA，
我要用formula去開發產品" -- build one shared library of real, well-known
finance/math/statistics formulas that every future product feature can
call into, instead of re-deriving/re-implementing the same math inline
each time a new engine gets built).

Design principles:
  1. Every function here is PURE -- it takes plain numbers/lists and
     returns plain numbers/lists/dicts. No network calls, no DB access,
     no dependency on any other XFINLAB service. This is deliberate: it
     is what makes these genuinely reusable "building blocks" rather
     than another OHLC-fetching engine coupled to one specific page.
     Existing engines (technical_analysis_service.py, backtest_service.py,
     market_structure_engine.py, smart_beta_service.py, risk_score_
     service.py, fundamentals_service.py) already do the "fetch real
     market data + apply formula + format for one UI" work -- this module
     is the formula layer underneath all of that, not a replacement for
     any of it. Where a formula already has a live implementation in one
     of those files (e.g. RSI, MACD, ATR), the version here is kept as
     the same well-known formula so results match, but is NOT imported
     into this file to avoid a two-way dependency -- callers pick
     whichever entry point suits them.
  2. Every function has a docstring stating: what it computes, the
     textbook formula, and a typical use case. This file doubles as the
     source of truth for services/formula_catalog.py's public catalog
     metadata (see that file for the human-readable directory used by
     api/formulas.py and formula-engine.html).
  3. No formula here produces investment advice or a BUY/SELL signal --
     consistent with this project's existing Paddle-compliance stance
     (see docs/paddle_compliance notes elsewhere in the codebase): these
     are neutral mathematical/statistical computations, full stop. Any
     product built on top of this library is responsible for its own
     disclaimers, same as every other engine in this codebase already is.

Organized into 7 sections:
  A. Technical Indicators
  B. Risk & Performance Metrics
  C. Options Pricing & Derivatives
  D. Portfolio Theory
  E. Time Value of Money / General Finance Math
  F. Statistics & Probability
  G. Market Structure / Chart Math
"""

import math
from typing import Sequence


# ============================================================
# A. TECHNICAL INDICATORS
# ============================================================

def sma(values: Sequence[float], period: int) -> list:
    """Simple Moving Average: SMA_t = (1/n) * sum(price_{t-n+1}..price_t).
    Trend-following baseline used to smooth noisy price series."""
    out = []
    for i in range(len(values)):
        if i + 1 < period:
            out.append(None)
        else:
            out.append(sum(values[i + 1 - period:i + 1]) / period)
    return out


def ema(values: Sequence[float], period: int) -> list:
    """Exponential Moving Average: EMA_t = price_t * k + EMA_{t-1} * (1-k),
    k = 2/(period+1). Weights recent prices more heavily than SMA, so it
    reacts faster to new information -- the base of MACD, SuperTrend, etc."""
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for i in range(1, len(values)):
        out.append(values[i] * k + out[-1] * (1 - k))
    return out


def wma(values: Sequence[float], period: int) -> list:
    """Weighted Moving Average: linearly weights the most recent n prices
    highest (weight n) down to the oldest (weight 1), sum(price_i * w_i) /
    sum(w_i). A middle ground between SMA (equal weight) and EMA."""
    out = []
    denom = period * (period + 1) / 2
    for i in range(len(values)):
        if i + 1 < period:
            out.append(None)
        else:
            window = values[i + 1 - period:i + 1]
            out.append(sum(w * v for w, v in zip(range(1, period + 1), window)) / denom)
    return out


def rsi(closes: Sequence[float], period: int = 14) -> list:
    """Relative Strength Index: RSI = 100 - 100/(1+RS), RS = avg_gain/avg_loss
    over `period` bars (Wilder's smoothing). Bounded 0-100; conventionally
    >70 read as overbought, <30 oversold -- a momentum/mean-reversion
    magnitude measure, not a signal by itself."""
    if len(closes) < period + 1:
        return [None] * len(closes)
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    out = [None] * period
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rs = avg_gain / avg_loss if avg_loss else float("inf")
    out.append(100 - 100 / (1 + rs))
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss else float("inf")
        out.append(100 - 100 / (1 + rs))
    return out


def macd(closes: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """Moving Average Convergence Divergence: MACD line = EMA_fast - EMA_slow,
    signal line = EMA(MACD, signal), histogram = MACD - signal. Classic
    trend/momentum indicator; crossovers of MACD vs signal are the
    conventional read (not asserted as advice here)."""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema(macd_line, signal)
    hist = [m - s for m, s in zip(macd_line, signal_line)]
    return {"macd": macd_line, "signal": signal_line, "histogram": hist}


def bollinger_bands(closes: Sequence[float], period: int = 20, num_std: float = 2.0) -> dict:
    """Bollinger Bands: middle = SMA(n), upper/lower = middle +/- (num_std *
    rolling std dev). Volatility envelope -- bands widen in high-volatility
    regimes, narrow in low-volatility ("squeeze") regimes."""
    mid = sma(closes, period)
    upper, lower = [], []
    for i in range(len(closes)):
        if i + 1 < period:
            upper.append(None)
            lower.append(None)
            continue
        window = closes[i + 1 - period:i + 1]
        m = sum(window) / period
        var = sum((x - m) ** 2 for x in window) / period
        sd = math.sqrt(var)
        upper.append(m + num_std * sd)
        lower.append(m - num_std * sd)
    return {"middle": mid, "upper": upper, "lower": lower}


def stochastic_oscillator(highs: Sequence[float], lows: Sequence[float],
                           closes: Sequence[float], period: int = 14, smooth_k: int = 3) -> dict:
    """Stochastic Oscillator: %K = 100 * (close - lowest_low_n) /
    (highest_high_n - lowest_low_n), %D = SMA(%K, smooth_k). Momentum
    oscillator comparing a close to its recent range, bounded 0-100."""
    k_raw = []
    for i in range(len(closes)):
        if i + 1 < period:
            k_raw.append(None)
            continue
        hh = max(highs[i + 1 - period:i + 1])
        ll = min(lows[i + 1 - period:i + 1])
        k_raw.append(100 * (closes[i] - ll) / (hh - ll) if hh != ll else 50.0)
    valid = [v for v in k_raw if v is not None]
    d_valid = sma(valid, smooth_k)
    d = [None] * (len(k_raw) - len(d_valid)) + d_valid
    return {"k": k_raw, "d": d}


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> list:
    """Average True Range: TR = max(high-low, |high-prev_close|,
    |low-prev_close|), ATR = Wilder-smoothed average of TR over `period`.
    Pure volatility measure (no direction), commonly used to size stops."""
    tr = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    if len(tr) < period:
        return [None] * len(tr)
    out = [None] * (period - 1)
    cur = sum(tr[:period]) / period
    out.append(cur)
    for i in range(period, len(tr)):
        cur = (cur * (period - 1) + tr[i]) / period
        out.append(cur)
    return out


def adx(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> list:
    """Average Directional Index: measures trend STRENGTH (not direction)
    from smoothed +DM/-DM directional movement and the ATR-normalized
    directional index (DX). 0-100 scale; >25 conventionally read as
    "trending", <20 as "range-bound"."""
    plus_dm, minus_dm, tr = [], [], [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > down and up > 0) else 0)
        minus_dm.append(down if (down > up and down > 0) else 0)
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    if len(tr) < period + 1:
        return [None] * len(closes)
    atr_v = sum(tr[:period]) / period
    plus_v = sum(plus_dm[:period]) / period
    minus_v = sum(minus_dm[:period]) / period
    dx_list = []
    for i in range(period, len(plus_dm)):
        atr_v = (atr_v * (period - 1) + tr[i]) / period
        plus_v = (plus_v * (period - 1) + plus_dm[i]) / period
        minus_v = (minus_v * (period - 1) + minus_dm[i]) / period
        plus_di = 100 * plus_v / atr_v if atr_v else 0
        minus_di = 100 * minus_v / atr_v if atr_v else 0
        dx_list.append(100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) else 0)
    adx_vals = sma(dx_list, period)
    return [None] * (len(closes) - len(adx_vals)) + adx_vals


def cci(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 20) -> list:
    """Commodity Channel Index: CCI = (typical_price - SMA(tp,n)) /
    (0.015 * mean_deviation). typical_price = (H+L+C)/3. Measures how far
    price has deviated from its statistical average; the 0.015 constant
    scales so ~70-80% of values fall within +/-100."""
    tp = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    out = []
    for i in range(len(tp)):
        if i + 1 < period:
            out.append(None)
            continue
        window = tp[i + 1 - period:i + 1]
        m = sum(window) / period
        mean_dev = sum(abs(x - m) for x in window) / period
        out.append((tp[i] - m) / (0.015 * mean_dev) if mean_dev else 0)
    return out


def williams_r(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> list:
    """Williams %R: %R = -100 * (highest_high_n - close) /
    (highest_high_n - lowest_low_n). Inverse-scaled cousin of the
    Stochastic Oscillator, bounded -100 to 0."""
    out = []
    for i in range(len(closes)):
        if i + 1 < period:
            out.append(None)
            continue
        hh = max(highs[i + 1 - period:i + 1])
        ll = min(lows[i + 1 - period:i + 1])
        out.append(-100 * (hh - closes[i]) / (hh - ll) if hh != ll else -50.0)
    return out


def obv(closes: Sequence[float], volumes: Sequence[float]) -> list:
    """On-Balance Volume: running total that adds today's volume if close
    rose, subtracts it if close fell. A cumulative volume-flow proxy for
    whether buying or selling pressure has been dominant."""
    out = [volumes[0]]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            out.append(out[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            out.append(out[-1] - volumes[i])
        else:
            out.append(out[-1])
    return out


def vwap(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], volumes: Sequence[float]) -> list:
    """Volume-Weighted Average Price: cumulative(typical_price * volume) /
    cumulative(volume). Session-anchored benchmark price weighting each
    bar by how much volume traded there."""
    tp = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    cum_pv, cum_v, out = 0.0, 0.0, []
    for p, v in zip(tp, volumes):
        cum_pv += p * v
        cum_v += v
        out.append(cum_pv / cum_v if cum_v else p)
    return out


def money_flow_index(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
                      volumes: Sequence[float], period: int = 14) -> list:
    """Money Flow Index: "volume-weighted RSI". Raw money flow = typical_price
    * volume; positive/negative flow classified by whether typical price
    rose/fell; MFI = 100 - 100/(1 + money_flow_ratio). Bounded 0-100."""
    tp = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    raw_flow = [t * v for t, v in zip(tp, volumes)]
    out = [None] * period
    for i in range(period, len(tp)):
        pos, neg = 0.0, 0.0
        for j in range(i - period + 1, i + 1):
            if tp[j] > tp[j - 1]:
                pos += raw_flow[j]
            elif tp[j] < tp[j - 1]:
                neg += raw_flow[j]
        ratio = pos / neg if neg else float("inf")
        out.append(100 - 100 / (1 + ratio))
    return out


def rate_of_change(closes: Sequence[float], period: int = 12) -> list:
    """Rate of Change (ROC): 100 * (close_t - close_{t-n}) / close_{t-n}.
    Pure momentum measure -- percentage price change over a fixed lookback."""
    out = [None] * period
    for i in range(period, len(closes)):
        out.append(100 * (closes[i] - closes[i - period]) / closes[i - period])
    return out


def parabolic_sar(highs: Sequence[float], lows: Sequence[float], af_step: float = 0.02, af_max: float = 0.2) -> list:
    """Parabolic SAR (Stop and Reverse): trailing stop that accelerates
    toward price as a trend extends. SAR_t = SAR_{t-1} + AF*(EP - SAR_{t-1}),
    where EP is the extreme point of the current trend and AF (acceleration
    factor) increases by af_step each time a new EP is made, capped at af_max."""
    if len(highs) < 2:
        return [None] * len(highs)
    trend_up = highs[1] >= highs[0]
    sar = lows[0] if trend_up else highs[0]
    ep = highs[0] if trend_up else lows[0]
    af = af_step
    out = [sar]
    for i in range(1, len(highs)):
        sar = sar + af * (ep - sar)
        if trend_up:
            if lows[i] < sar:
                trend_up, sar, ep, af = False, ep, lows[i], af_step
            else:
                if highs[i] > ep:
                    ep, af = highs[i], min(af + af_step, af_max)
        else:
            if highs[i] > sar:
                trend_up, sar, ep, af = True, ep, highs[i], af_step
            else:
                if lows[i] < ep:
                    ep, af = lows[i], min(af + af_step, af_max)
        out.append(sar)
    return out


def donchian_channel(highs: Sequence[float], lows: Sequence[float], period: int = 20) -> dict:
    """Donchian Channel: upper = highest_high_n, lower = lowest_low_n,
    middle = average of the two. The basis of classic turtle-trading
    breakout systems -- a pure price-range envelope, no averaging math."""
    upper, lower, mid = [], [], []
    for i in range(len(highs)):
        if i + 1 < period:
            upper.append(None)
            lower.append(None)
            mid.append(None)
            continue
        hh = max(highs[i + 1 - period:i + 1])
        ll = min(lows[i + 1 - period:i + 1])
        upper.append(hh)
        lower.append(ll)
        mid.append((hh + ll) / 2)
    return {"upper": upper, "lower": lower, "middle": mid}


def keltner_channel(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
                     period: int = 20, atr_mult: float = 2.0) -> dict:
    """Keltner Channel: middle = EMA(close,n), upper/lower = middle +/-
    (atr_mult * ATR(n)). Like Bollinger Bands but uses ATR instead of
    standard deviation for the envelope width, so it responds to
    true-range volatility rather than close-to-close volatility."""
    mid = ema(closes, period)
    atr_v = atr(highs, lows, closes, period)
    upper = [m + atr_mult * a if a is not None else None for m, a in zip(mid, atr_v)]
    lower = [m - atr_mult * a if a is not None else None for m, a in zip(mid, atr_v)]
    return {"middle": mid, "upper": upper, "lower": lower}


# ============================================================
# B. RISK & PERFORMANCE METRICS
# ============================================================

def sharpe_ratio(returns: Sequence[float], risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    """Sharpe Ratio: (mean(excess_return) / std(excess_return)) *
    sqrt(periods_per_year). Risk-adjusted return per unit of TOTAL
    volatility (upside and downside both penalized equally)."""
    excess = [r - risk_free_rate / periods_per_year for r in returns]
    m = sum(excess) / len(excess)
    var = sum((x - m) ** 2 for x in excess) / len(excess)
    sd = math.sqrt(var)
    return (m / sd) * math.sqrt(periods_per_year) if sd else 0.0


def sortino_ratio(returns: Sequence[float], risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    """Sortino Ratio: like Sharpe, but the denominator only counts
    DOWNSIDE deviation (returns below the target/0), not total volatility
    -- a fairer risk-adjusted measure when returns are asymmetric, since
    upside volatility isn't penalized."""
    excess = [r - risk_free_rate / periods_per_year for r in returns]
    m = sum(excess) / len(excess)
    downside = [min(x, 0) ** 2 for x in excess]
    dd = math.sqrt(sum(downside) / len(downside))
    return (m / dd) * math.sqrt(periods_per_year) if dd else 0.0


def treynor_ratio(portfolio_return: float, risk_free_rate: float, beta: float) -> float:
    """Treynor Ratio: (portfolio_return - risk_free_rate) / beta. Like
    Sharpe but divides by systematic risk (beta) instead of total
    volatility -- appropriate for an already-diversified portfolio where
    only market risk should matter."""
    return (portfolio_return - risk_free_rate) / beta if beta else 0.0


def calmar_ratio(annual_return: float, max_drawdown_pct: float) -> float:
    """Calmar Ratio: annual_return / abs(max_drawdown). Compares reward to
    the worst pain actually experienced, rather than to average
    volatility -- popular for evaluating trend-following strategies."""
    return annual_return / abs(max_drawdown_pct) if max_drawdown_pct else 0.0


def max_drawdown(equity_curve: Sequence[float]) -> dict:
    """Maximum Drawdown: largest peak-to-trough decline in an equity curve,
    MDD = min((value_t - running_peak) / running_peak). Returns both the
    percentage and the peak/trough index for reference."""
    peak = equity_curve[0]
    peak_idx = 0
    worst, worst_peak_idx, worst_trough_idx = 0.0, 0, 0
    for i, v in enumerate(equity_curve):
        if v > peak:
            peak, peak_idx = v, i
        dd = (v - peak) / peak if peak else 0
        if dd < worst:
            worst, worst_peak_idx, worst_trough_idx = dd, peak_idx, i
    return {"max_drawdown_pct": worst, "peak_index": worst_peak_idx, "trough_index": worst_trough_idx}


def value_at_risk_historical(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Historical VaR: the loss at the `confidence` percentile of the
    empirical (actually observed) return distribution -- no distributional
    assumption, just sorts historical returns and reads off the tail."""
    sorted_r = sorted(returns)
    idx = int((1 - confidence) * len(sorted_r))
    return sorted_r[max(0, idx)]


def value_at_risk_parametric(mean_return: float, std_return: float, confidence: float = 0.95) -> float:
    """Parametric (Gaussian) VaR: VaR = mean - z(confidence) * std, using
    the normal-distribution assumption. z_0.95≈1.645, z_0.99≈2.326.
    Faster than historical VaR but understates tail risk if returns
    aren't actually normal (they usually aren't -- fat tails)."""
    z = _norm_ppf(confidence)
    return mean_return - z * std_return


def conditional_value_at_risk(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Conditional VaR / Expected Shortfall: the AVERAGE loss in the worst
    (1-confidence) tail of outcomes, not just the cutoff point VaR gives
    you -- answers "if it's bad, how bad on average", which VaR alone
    doesn't."""
    sorted_r = sorted(returns)
    cutoff = max(1, int((1 - confidence) * len(sorted_r)))
    tail = sorted_r[:cutoff]
    return sum(tail) / len(tail) if tail else 0.0


def beta_coefficient(asset_returns: Sequence[float], market_returns: Sequence[float]) -> float:
    """Beta: Cov(asset, market) / Var(market). Measures an asset's
    sensitivity to overall market moves -- beta=1 moves with the market,
    >1 amplifies it, <1 dampens it, negative moves opposite."""
    cov = _covariance(asset_returns, market_returns)
    var = _variance(market_returns)
    return cov / var if var else 0.0


def jensens_alpha(portfolio_return: float, risk_free_rate: float, beta: float, market_return: float) -> float:
    """Jensen's Alpha: portfolio_return - [risk_free + beta*(market_return
    - risk_free)]. The CAPM-predicted return is the bracketed term; alpha
    is whatever excess return isn't explained by market exposure alone."""
    expected = risk_free_rate + beta * (market_return - risk_free_rate)
    return portfolio_return - expected


def information_ratio(portfolio_returns: Sequence[float], benchmark_returns: Sequence[float]) -> float:
    """Information Ratio: mean(active_return) / std(active_return), where
    active_return = portfolio - benchmark per period. Measures consistency
    of outperformance versus a benchmark, independent of the benchmark's
    own volatility."""
    active = [p - b for p, b in zip(portfolio_returns, benchmark_returns)]
    m = sum(active) / len(active)
    sd = math.sqrt(_variance(active))
    return m / sd if sd else 0.0


def annualized_volatility(returns: Sequence[float], periods_per_year: int = 252) -> float:
    """Annualized Volatility: std(period_returns) * sqrt(periods_per_year).
    Converts a per-period (e.g. daily) standard deviation into a
    comparable annual figure, assuming i.i.d. returns."""
    return math.sqrt(_variance(returns)) * math.sqrt(periods_per_year)


def downside_deviation(returns: Sequence[float], target: float = 0.0) -> float:
    """Downside Deviation: sqrt(mean(min(return-target, 0)^2)). Like
    standard deviation but only counts shortfalls below a target return
    -- the denominator used inside the Sortino Ratio."""
    sq = [min(r - target, 0) ** 2 for r in returns]
    return math.sqrt(sum(sq) / len(sq))


def r_squared(asset_returns: Sequence[float], benchmark_returns: Sequence[float]) -> float:
    """R-squared: square of the Pearson correlation between asset and
    benchmark returns. Fraction of an asset's variance "explained by" the
    benchmark's moves -- high R² means beta is a meaningful description,
    low R² means most of the asset's variance is idiosyncratic."""
    r = pearson_correlation(asset_returns, benchmark_returns)
    return r ** 2


def ulcer_index(equity_curve: Sequence[float]) -> float:
    """Ulcer Index: sqrt(mean(drawdown_pct_t^2)) across the whole equity
    curve, not just the single worst drawdown like Max Drawdown does --
    penalizes both DEPTH and DURATION of drawdowns, since a long shallow
    slump contributes as much as a short sharp one of similar RMS size."""
    peak = equity_curve[0]
    sq_dd = []
    for v in equity_curve:
        if v > peak:
            peak = v
        dd_pct = 100 * (v - peak) / peak if peak else 0
        sq_dd.append(dd_pct ** 2)
    return math.sqrt(sum(sq_dd) / len(sq_dd))


# ============================================================
# C. OPTIONS PRICING & DERIVATIVES
# ============================================================

def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function via the error
    function -- Phi(x) = 0.5 * (1 + erf(x/sqrt(2)))."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function:
    phi(x) = (1/sqrt(2*pi)) * exp(-x^2/2)."""
    return (1 / math.sqrt(2 * math.pi)) * math.exp(-x ** 2 / 2)


def _norm_ppf(p: float) -> float:
    """Standard normal inverse CDF (quantile function) via Acklam's
    rational approximation -- avoids needing scipy for a single lookup."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    p_low, p_high = 0.02425, 1 - 0.02425
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
           ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


def black_scholes(spot: float, strike: float, time_to_expiry_years: float, rate: float,
                   volatility: float, option_type: str = "call") -> float:
    """Black-Scholes Option Price: the foundational closed-form model for
    European option pricing. d1 = [ln(S/K) + (r + sigma^2/2)T] / (sigma*sqrt(T)),
    d2 = d1 - sigma*sqrt(T). Call = S*N(d1) - K*e^(-rT)*N(d2). Put via
    put-call parity. Assumes constant volatility/rate, no dividends,
    European exercise -- a starting reference model, not a live quote."""
    if time_to_expiry_years <= 0:
        return max(0.0, spot - strike) if option_type == "call" else max(0.0, strike - spot)
    d1 = (math.log(spot / strike) + (rate + volatility ** 2 / 2) * time_to_expiry_years) / \
         (volatility * math.sqrt(time_to_expiry_years))
    d2 = d1 - volatility * math.sqrt(time_to_expiry_years)
    if option_type == "call":
        return spot * _norm_cdf(d1) - strike * math.exp(-rate * time_to_expiry_years) * _norm_cdf(d2)
    return strike * math.exp(-rate * time_to_expiry_years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def black_scholes_greeks(spot: float, strike: float, time_to_expiry_years: float, rate: float,
                          volatility: float, option_type: str = "call") -> dict:
    """Black-Scholes Greeks: sensitivities of option price to each input.
    Delta = d(price)/d(spot), Gamma = d(delta)/d(spot), Theta = d(price)/d(time)
    [reported per calendar day], Vega = d(price)/d(volatility) [per 1% vol],
    Rho = d(price)/d(rate) [per 1% rate]."""
    if time_to_expiry_years <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
    T, sig = time_to_expiry_years, volatility
    d1 = (math.log(spot / strike) + (rate + sig ** 2 / 2) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    if option_type == "call":
        delta = _norm_cdf(d1)
        theta = (-(spot * _norm_pdf(d1) * sig) / (2 * math.sqrt(T)) -
                 rate * strike * math.exp(-rate * T) * _norm_cdf(d2)) / 365
        rho = strike * T * math.exp(-rate * T) * _norm_cdf(d2) / 100
    else:
        delta = _norm_cdf(d1) - 1
        theta = (-(spot * _norm_pdf(d1) * sig) / (2 * math.sqrt(T)) +
                 rate * strike * math.exp(-rate * T) * _norm_cdf(-d2)) / 365
        rho = -strike * T * math.exp(-rate * T) * _norm_cdf(-d2) / 100
    gamma = _norm_pdf(d1) / (spot * sig * math.sqrt(T))
    vega = spot * _norm_pdf(d1) * math.sqrt(T) / 100
    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega, "rho": rho}


def binomial_option_price(spot: float, strike: float, time_to_expiry_years: float, rate: float,
                           volatility: float, steps: int = 100, option_type: str = "call",
                           american: bool = False) -> float:
    """Binomial (Cox-Ross-Rubinstein) Option Pricing: builds a discrete
    lattice of up/down price moves (u=e^(sigma*sqrt(dt)), d=1/u) and
    backward-induces the option value at each node under risk-neutral
    probability p=(e^(r*dt)-d)/(u-d). Handles American early exercise
    (Black-Scholes cannot) by taking max(intrinsic, continuation) at each
    node when american=True."""
    dt = time_to_expiry_years / steps
    u = math.exp(volatility * math.sqrt(dt))
    d = 1 / u
    p = (math.exp(rate * dt) - d) / (u - d)
    disc = math.exp(-rate * dt)
    prices = [spot * u ** j * d ** (steps - j) for j in range(steps + 1)]
    if option_type == "call":
        values = [max(0.0, pr - strike) for pr in prices]
    else:
        values = [max(0.0, strike - pr) for pr in prices]
    for step in range(steps - 1, -1, -1):
        new_values = []
        for j in range(step + 1):
            continuation = disc * (p * values[j + 1] + (1 - p) * values[j])
            if american:
                node_price = spot * u ** j * d ** (step - j)
                intrinsic = max(0.0, node_price - strike) if option_type == "call" else max(0.0, strike - node_price)
                new_values.append(max(continuation, intrinsic))
            else:
                new_values.append(continuation)
        values = new_values
    return values[0]


def put_call_parity(call_price: float = None, put_price: float = None, spot: float = None,
                     strike: float = None, rate: float = None, time_to_expiry_years: float = None) -> float:
    """Put-Call Parity: C - P = S - K*e^(-rT). A no-arbitrage relationship
    -- given any 5 of {call, put, spot, strike, discount factor}, solves
    for the missing one. Here: solves for whichever of call_price/put_price
    is None."""
    discounted_strike = strike * math.exp(-rate * time_to_expiry_years)
    if call_price is None:
        return put_price + spot - discounted_strike
    if put_price is None:
        return call_price - spot + discounted_strike
    raise ValueError("Provide exactly one of call_price/put_price as None to solve for it")


def implied_volatility(market_price: float, spot: float, strike: float, time_to_expiry_years: float,
                        rate: float, option_type: str = "call", tol: float = 1e-6, max_iter: int = 100) -> float:
    """Implied Volatility: the sigma that makes Black-Scholes match an
    observed market price, found via Newton-Raphson (using Vega as the
    derivative) since Black-Scholes has no closed-form inverse for sigma."""
    sigma = 0.3
    for _ in range(max_iter):
        price = black_scholes(spot, strike, time_to_expiry_years, rate, sigma, option_type)
        vega = black_scholes_greeks(spot, strike, time_to_expiry_years, rate, sigma, option_type)["vega"] * 100
        diff = price - market_price
        if abs(diff) < tol or vega == 0:
            break
        sigma -= diff / vega
        sigma = max(0.001, sigma)
    return sigma


# ============================================================
# D. PORTFOLIO THEORY
# ============================================================

def capm_expected_return(risk_free_rate: float, beta: float, market_return: float) -> float:
    """Capital Asset Pricing Model: E[R] = Rf + beta*(E[Rm] - Rf). The
    textbook baseline for what return an asset "should" offer given only
    its market-risk (beta) exposure."""
    return risk_free_rate + beta * (market_return - risk_free_rate)


def portfolio_variance_two_asset(w1: float, w2: float, var1: float, var2: float, cov12: float) -> float:
    """Two-Asset Portfolio Variance: Var_p = w1^2*Var1 + w2^2*Var2 +
    2*w1*w2*Cov12. The core Markowitz insight -- imperfect correlation
    between assets (Cov12 < the product of their std devs) lets
    diversification reduce total risk below either asset's own risk."""
    return w1 ** 2 * var1 + w2 ** 2 * var2 + 2 * w1 * w2 * cov12


def portfolio_return(weights: Sequence[float], returns: Sequence[float]) -> float:
    """Portfolio Expected Return: sum(weight_i * expected_return_i) --
    a simple weighted average of each holding's expected return."""
    return sum(w * r for w, r in zip(weights, returns))


def portfolio_variance(weights: Sequence[float], cov_matrix: Sequence[Sequence[float]]) -> float:
    """N-Asset Portfolio Variance: w^T * Cov * w (matrix form of the
    two-asset case). Requires the full covariance matrix between every
    pair of holdings, not just their individual variances."""
    n = len(weights)
    total = 0.0
    for i in range(n):
        for j in range(n):
            total += weights[i] * weights[j] * cov_matrix[i][j]
    return total


def kelly_criterion(win_probability: float, win_loss_ratio: float) -> float:
    """Kelly Criterion: f* = p - (1-p)/b, where p = win probability, b =
    win/loss ratio (avg win size / avg loss size). The fraction of
    capital that maximizes long-run geometric growth rate for a
    repeated bet with these odds -- notoriously aggressive at full size,
    commonly used at a fraction (e.g. "half-Kelly") in practice."""
    return win_probability - (1 - win_probability) / win_loss_ratio if win_loss_ratio else 0.0


def fama_french_3factor(risk_free_rate: float, beta_mkt: float, market_return: float,
                         beta_smb: float, smb_return: float, beta_hml: float, hml_return: float) -> float:
    """Fama-French 3-Factor Model: E[R] = Rf + beta_mkt*(Rm-Rf) +
    beta_smb*SMB + beta_hml*HML. Extends CAPM with two empirically-observed
    return premia: SMB ("small minus big" -- small caps historically
    outperform), HML ("high minus low" book-to-market -- value stocks
    historically outperform growth)."""
    return risk_free_rate + beta_mkt * (market_return - risk_free_rate) + beta_smb * smb_return + beta_hml * hml_return


def min_variance_weights_two_asset(var1: float, var2: float, cov12: float) -> dict:
    """Minimum-Variance Two-Asset Weights: w1* = (Var2 - Cov12) /
    (Var1 + Var2 - 2*Cov12), w2* = 1 - w1*. The closed-form weighting
    that minimizes total portfolio variance for exactly two assets
    (the simplest point on the Markowitz efficient frontier)."""
    denom = var1 + var2 - 2 * cov12
    w1 = (var2 - cov12) / denom if denom else 0.5
    return {"w1": w1, "w2": 1 - w1}


def covariance_matrix(returns_matrix: Sequence[Sequence[float]]) -> list:
    """Covariance Matrix: pairwise Cov(asset_i, asset_j) for every asset
    in returns_matrix (one row per asset, one column per period). The
    required input for full-N-asset Markowitz optimization."""
    n = len(returns_matrix)
    return [[_covariance(returns_matrix[i], returns_matrix[j]) for j in range(n)] for i in range(n)]


# ============================================================
# E. TIME VALUE OF MONEY / GENERAL FINANCE MATH
# ============================================================

def present_value(future_value: float, rate: float, periods: float) -> float:
    """Present Value: PV = FV / (1+r)^n. What a future cash flow is worth
    today given a discount rate -- the foundation of all DCF valuation."""
    return future_value / (1 + rate) ** periods


def future_value(present_value_: float, rate: float, periods: float) -> float:
    """Future Value: FV = PV * (1+r)^n. What a present sum grows to under
    compound interest -- the inverse of present_value()."""
    return present_value_ * (1 + rate) ** periods


def net_present_value(rate: float, cash_flows: Sequence[float]) -> float:
    """Net Present Value: NPV = sum(CF_t / (1+r)^t) for t=0,1,2,... where
    cash_flows[0] is typically the (negative) initial investment. Positive
    NPV means the cash flows are worth more than the discount rate demands."""
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cash_flows))


def internal_rate_of_return(cash_flows: Sequence[float], guess: float = 0.1, tol: float = 1e-6, max_iter: int = 1000) -> float:
    """Internal Rate of Return: the discount rate r that makes NPV(r) = 0,
    found via Newton-Raphson on net_present_value(). The "break-even"
    discount rate a project/investment implies."""
    r = guess
    for _ in range(max_iter):
        npv = net_present_value(r, cash_flows)
        d_npv = sum(-t * cf / (1 + r) ** (t + 1) for t, cf in enumerate(cash_flows))
        if d_npv == 0:
            break
        r_new = r - npv / d_npv
        if abs(r_new - r) < tol:
            return r_new
        r = r_new
    return r


def cagr(begin_value: float, end_value: float, years: float) -> float:
    """Compound Annual Growth Rate: (end/begin)^(1/years) - 1. The
    constant annual growth rate that would take begin_value to
    end_value over the period -- smooths out year-to-year volatility
    into one comparable number."""
    return (end_value / begin_value) ** (1 / years) - 1 if begin_value and years else 0.0


def compound_interest(principal: float, rate: float, periods_per_year: int, years: float) -> float:
    """Compound Interest: A = P*(1 + r/n)^(n*t). Final amount after
    compounding `periods_per_year` times a year for `years` years."""
    return principal * (1 + rate / periods_per_year) ** (periods_per_year * years)


def loan_payment(principal: float, rate_per_period: float, num_periods: int) -> float:
    """Loan/Mortgage Amortization Payment: PMT = P * r*(1+r)^n /
    ((1+r)^n - 1). The fixed periodic payment that fully repays a loan
    (principal + interest) over num_periods, given a per-period rate."""
    if rate_per_period == 0:
        return principal / num_periods
    return principal * (rate_per_period * (1 + rate_per_period) ** num_periods) / \
           ((1 + rate_per_period) ** num_periods - 1)


def gordon_growth_model(next_dividend: float, required_return: float, growth_rate: float) -> float:
    """Gordon Growth (Dividend Discount) Model: P = D1 / (r - g). Values a
    stock as the present value of an infinite stream of dividends growing
    at a constant rate g, discounted at required return r. Requires r > g
    to converge -- a simplification, not a full valuation model."""
    if required_return <= growth_rate:
        raise ValueError("required_return must exceed growth_rate for the model to converge")
    return next_dividend / (required_return - growth_rate)


def discounted_cash_flow(cash_flows: Sequence[float], discount_rate: float, terminal_growth: float = None) -> float:
    """Discounted Cash Flow Valuation: sum of each projected cash flow's
    present_value(), optionally plus a terminal value (Gordon Growth of
    the final year's cash flow) if terminal_growth is given. The standard
    intrinsic-value framework behind most equity valuation."""
    total = sum(present_value(cf, discount_rate, t + 1) for t, cf in enumerate(cash_flows))
    if terminal_growth is not None:
        terminal_value = gordon_growth_model(cash_flows[-1] * (1 + terminal_growth), discount_rate, terminal_growth)
        total += present_value(terminal_value, discount_rate, len(cash_flows))
    return total


# ============================================================
# F. STATISTICS & PROBABILITY
# ============================================================

def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _variance(values: Sequence[float]) -> float:
    m = _mean(values)
    return sum((x - m) ** 2 for x in values) / len(values)


def _covariance(a: Sequence[float], b: Sequence[float]) -> float:
    ma, mb = _mean(a), _mean(b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a)


def z_score(value: float, mean: float, std_dev: float) -> float:
    """Z-Score: (value - mean) / std_dev. How many standard deviations a
    value sits from the mean -- the universal "how unusual is this"
    normalization used across finance and statistics."""
    return (value - mean) / std_dev if std_dev else 0.0


def normal_pdf(x: float, mean: float = 0.0, std_dev: float = 1.0) -> float:
    """Normal Distribution PDF: probability density of x under a Normal(mean,
    std_dev) distribution -- phi((x-mean)/std_dev)/std_dev."""
    z = (x - mean) / std_dev
    return _norm_pdf(z) / std_dev


def normal_cdf(x: float, mean: float = 0.0, std_dev: float = 1.0) -> float:
    """Normal Distribution CDF: P(X <= x) under a Normal(mean, std_dev)
    distribution -- the probability of observing a value at or below x."""
    return _norm_cdf((x - mean) / std_dev)


def linear_regression(x: Sequence[float], y: Sequence[float]) -> dict:
    """Simple Linear Regression: slope = Cov(x,y)/Var(x), intercept =
    mean(y) - slope*mean(x), via ordinary least squares. The basis of
    trendlines, beta estimation, and countless other fits in this codebase."""
    slope = _covariance(x, y) / _variance(x) if _variance(x) else 0.0
    intercept = _mean(y) - slope * _mean(x)
    return {"slope": slope, "intercept": intercept}


def pearson_correlation(a: Sequence[float], b: Sequence[float]) -> float:
    """Pearson Correlation Coefficient: Cov(a,b) / (std(a)*std(b)). Bounded
    -1 to 1, measures linear co-movement strength/direction between two
    series -- the basis of beta, R², and diversification math."""
    sd_a, sd_b = math.sqrt(_variance(a)), math.sqrt(_variance(b))
    return _covariance(a, b) / (sd_a * sd_b) if (sd_a and sd_b) else 0.0


def standard_error(std_dev: float, sample_size: int) -> float:
    """Standard Error of the Mean: std_dev / sqrt(n). How precisely a
    sample mean estimates the true population mean -- shrinks as sample
    size grows, unlike std_dev itself."""
    return std_dev / math.sqrt(sample_size) if sample_size else 0.0


def confidence_interval(mean: float, std_error: float, confidence: float = 0.95) -> dict:
    """Confidence Interval: mean +/- z(confidence)*std_error, using the
    normal-approximation z-value (1.96 for 95%, 2.576 for 99%). The range
    expected to contain the true mean at the stated confidence level."""
    z = _norm_ppf(1 - (1 - confidence) / 2)
    margin = z * std_error
    return {"lower": mean - margin, "upper": mean + margin, "margin": margin}


def monte_carlo_gbm(spot: float, drift: float, volatility: float, time_years: float,
                     num_steps: int, num_paths: int, seed: int = None) -> list:
    """Monte Carlo Simulation (Geometric Brownian Motion): simulates
    num_paths price paths via S_{t+dt} = S_t * exp[(mu - sigma^2/2)*dt +
    sigma*sqrt(dt)*Z], Z~N(0,1) -- the same stochastic process Black-Scholes
    assumes, used here to generate scenario paths rather than a closed-form
    price. Uses Python's own `random` module (no numpy dependency)."""
    import random
    rng = random.Random(seed)
    dt = time_years / num_steps
    paths = []
    for _ in range(num_paths):
        path = [spot]
        for _ in range(num_steps):
            z = rng.gauss(0, 1)
            path.append(path[-1] * math.exp((drift - volatility ** 2 / 2) * dt + volatility * math.sqrt(dt) * z))
        paths.append(path)
    return paths


def kalman_filter_1d(observations: Sequence[float], process_variance: float = 1e-5,
                      measurement_variance: float = 1e-2) -> list:
    """1D Kalman Filter: recursively estimates the true underlying value
    from noisy observations. Predict: P = P_prev + Q. Update: K = P/(P+R),
    estimate = estimate_prev + K*(obs - estimate_prev), P = (1-K)*P. Q =
    process_variance (how much the true value can drift), R =
    measurement_variance (how noisy observations are). Used for smoothing
    noisy price/signal series with less lag than a moving average."""
    estimate = observations[0]
    error_est = 1.0
    out = [estimate]
    for obs in observations[1:]:
        error_est += process_variance
        kalman_gain = error_est / (error_est + measurement_variance)
        estimate = estimate + kalman_gain * (obs - estimate)
        error_est = (1 - kalman_gain) * error_est
        out.append(estimate)
    return out


def garch_1_1_variance(returns: Sequence[float], omega: float, alpha: float, beta: float) -> list:
    """GARCH(1,1) Conditional Variance: sigma_t^2 = omega + alpha*r_{t-1}^2
    + beta*sigma_{t-1}^2. Models volatility as itself time-varying and
    clustering (today's variance depends on yesterday's shock AND
    yesterday's variance) -- the standard model behind most modern
    volatility forecasting, more realistic than a constant-volatility
    assumption like Black-Scholes uses."""
    var = _variance(returns)
    out = [var]
    for r in returns[1:]:
        var = omega + alpha * r ** 2 + beta * var
        out.append(var)
    return out


# ============================================================
# G. MARKET STRUCTURE / CHART MATH
# ============================================================

_FIB_RATIOS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
_FIB_EXTENSION_RATIOS = [1.272, 1.618, 2.0, 2.618]


def fibonacci_retracement(swing_high: float, swing_low: float) -> dict:
    """Fibonacci Retracement Levels: swing_high - ratio*(swing_high -
    swing_low), for ratio in {0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0}.
    Derived from the Fibonacci sequence's convergent ratios; used to mark
    candidate pullback levels within a prior price swing."""
    diff = swing_high - swing_low
    return {f"{int(r * 1000) / 10}%": swing_high - r * diff for r in _FIB_RATIOS}


def fibonacci_extension(swing_high: float, swing_low: float, retracement_point: float) -> dict:
    """Fibonacci Extension Levels: retracement_point + ratio*(swing_high -
    swing_low), for ratio in {1.272, 1.618, 2.0, 2.618}. Projects
    candidate target levels BEYOND the original swing, anchored at a
    retracement point where the next leg is presumed to begin."""
    diff = swing_high - swing_low
    return {f"{r}": retracement_point + r * diff for r in _FIB_EXTENSION_RATIOS}


def pivot_points_classic(prev_high: float, prev_low: float, prev_close: float) -> dict:
    """Classic Pivot Points: PP = (H+L+C)/3, then R1/S1 = 2*PP-L / 2*PP-H,
    R2/S2 = PP+(H-L) / PP-(H-L), R3/S3 = H+2*(PP-L) / L-2*(H-PP). A
    session-independent set of candidate support/resistance levels derived
    purely from the prior period's range."""
    pp = (prev_high + prev_low + prev_close) / 3
    r1 = 2 * pp - prev_low
    s1 = 2 * pp - prev_high
    r2 = pp + (prev_high - prev_low)
    s2 = pp - (prev_high - prev_low)
    r3 = prev_high + 2 * (pp - prev_low)
    s3 = prev_low - 2 * (prev_high - pp)
    return {"pivot": pp, "r1": r1, "r2": r2, "r3": r3, "s1": s1, "s2": s2, "s3": s3}


def pivot_points_camarilla(prev_high: float, prev_low: float, prev_close: float) -> dict:
    """Camarilla Pivot Points: R/S levels = close +/- (range * multiplier),
    multipliers {1.1/12, 1.1/6, 1.1/4, 1.1/2} for level 1-4. Tighter,
    more clustered levels than classic pivots -- designed for intraday
    mean-reversion around the previous close rather than the full range."""
    rng = prev_high - prev_low
    return {
        "r1": prev_close + rng * 1.1 / 12, "s1": prev_close - rng * 1.1 / 12,
        "r2": prev_close + rng * 1.1 / 6, "s2": prev_close - rng * 1.1 / 6,
        "r3": prev_close + rng * 1.1 / 4, "s3": prev_close - rng * 1.1 / 4,
        "r4": prev_close + rng * 1.1 / 2, "s4": prev_close - rng * 1.1 / 2,
    }


def regression_channel(closes: Sequence[float]) -> dict:
    """Linear Regression Channel: fits an OLS trendline through closes
    (see linear_regression()), then bands it +/- 2*residual_std_dev to
    form a statistical support/resistance channel around the trend."""
    x = list(range(len(closes)))
    reg = linear_regression(x, closes)
    fitted = [reg["slope"] * xi + reg["intercept"] for xi in x]
    residuals = [c - f for c, f in zip(closes, fitted)]
    resid_std = math.sqrt(_variance(residuals))
    return {
        "midline": fitted,
        "upper": [f + 2 * resid_std for f in fitted],
        "lower": [f - 2 * resid_std for f in fitted],
        "slope": reg["slope"],
    }


# -- Gann Theory (2026-08-21, AJ: "江恩理論，加入所有ENGINE") --------------
# Classic W.D. Gann geometric/numerological techniques, same neutral-
# levels-only treatment as the Fibonacci/pivot functions above: no BUY/
# SELL signal, no claim of backtested edge -- these are the standard
# published formulas for the technique itself, nothing more.

_GANN_ANGLE_RATIOS = {
    "1x8": 1 / 8, "1x4": 1 / 4, "1x3": 1 / 3, "1x2": 1 / 2, "1x1": 1.0,
    "2x1": 2.0, "3x1": 3.0, "4x1": 4.0, "8x1": 8.0,
}
_GANN_SQ9_ANGLES = [45, 90, 135, 180, 225, 270, 315, 360]
_GANN_CYCLE_DAYS = [30, 45, 60, 90, 120, 144, 180, 270, 360]


def gann_angles(anchor_price: float, unit_slope: float, bars_elapsed: int, direction: str = "up") -> dict:
    """Gann Fan Angles: classic trendlines fanned out from a significant
    swing pivot at fixed price-per-time ratios -- 1x8, 1x4, 1x3, 1x2, 1x1
    (the master 45-degree line), 2x1, 3x1, 4x1, 8x1 (e.g. "2x1" rises 2
    price units per 1 time unit, steeper than 1x1; "1x2" rises 1 price
    unit per 2 time units, shallower). Gann angles have no universal
    scale -- `unit_slope` is the price-per-bar rate that defines this
    instrument/timeframe's own "1x1" line (callers typically derive it
    from the swing's own price range divided by its bar count, e.g.
    (swing_high - swing_low) / bars_in_swing). Returns each angle's
    projected price `bars_elapsed` bars after the anchor pivot;
    direction="up" fans upward from a swing low, "down" fans downward
    from a swing high."""
    sign = 1 if direction == "up" else -1
    return {
        name: anchor_price + sign * ratio * unit_slope * bars_elapsed
        for name, ratio in _GANN_ANGLE_RATIOS.items()
    }


def gann_square_of_9(price: float) -> dict:
    """Gann Square of Nine: root = sqrt(price), then for each angle in
    {45,90,135,180,225,270,315,360} degrees, level = (root +/- angle/180)^2
    -- the commonly published "trading formula" reduction of Gann's
    spiral-of-odd-squares (one full 360-degree rotation = +/-2 on the
    square root). Produces a symmetric ring of candidate resistance
    (rXXX, above price) and support (sXXX, below price) levels radiating
    from the anchor price."""
    root = math.sqrt(price)
    out = {}
    for a in _GANN_SQ9_ANGLES:
        out[f"r{a}"] = (root + a / 180) ** 2
        out[f"s{a}"] = max(0.0, (root - a / 180) ** 2)
    return out


def gann_time_cycles(pivot_index: int) -> dict:
    """Gann Time Cycles: classic anniversary/square-number day counts
    {30,45,60,90,120,144,180,270,360} projected forward from a significant
    pivot bar -- candidate future dates where price is more likely to
    change character (trend change, reversal, or acceleration), per
    Gann's time-price-squaring theory. `pivot_index` is any integer bar/
    day count (e.g. an OHLC DataFrame row index, or days-since-epoch);
    the caller maps the returned bar indices back to real calendar dates
    using whichever index their own price series uses. A mechanical
    day-count projection -- no claim of predictive power beyond the
    classical technique itself."""
    return {f"{d}d": pivot_index + d for d in _GANN_CYCLE_DAYS}
