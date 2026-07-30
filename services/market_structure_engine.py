"""
Market Structure Engine V2 (Level 1) -- 2026-07-30 upgrade.

Previously (see the old `TechnicalAnalysisService._market_structure()`,
still left in place below but no longer called): prior-structure was read
off just the last 2 swing highs/lows (HH+HL vs LH+LL vs mixed) and
BOS/CHOCH/liquidity-sweep were plain boolean event triggers with no
strength/quality measure at all -- "Bullish=True", not a score an AI or a
downstream Confidence composite can actually reason over.

This module quantifies that same real price-action geometry into
independent 0-100 sub-engine scores (matching the architecture proposal
the user posted, cross-checked against what real quant/prop-style
systems do: decompose structure into orthogonal, objectively-computed
features, THEN combine into a weighted composite -- never invert into a
single boolean too early). Every score here is a deterministic function
of real OHLCV data already fetched for this ticker (swing points, ATR,
volume, candle geometry) -- nothing here calls an LLM, guesses, or uses
data XFINLAB doesn't actually have.

2026-07-30, later same session -- Order Flow / Volume Profile / Institutional
Footprint added back in, PROXY-ONLY: the user asked for all 3. None of
this codebase's data sources (yfinance, Alpaca's free IEX feed) provide
level-2 order-book, tick, or dark-pool data, so a GENUINE order-flow,
volume-at-price, or institutional-footprint number still can't be
computed here -- faking one would be exactly the invented-looking-precise-
number problem this codebase's other modules (chart_pattern_service.py,
historical_analog_service.py, services/backtest_service.py) already
refuse to ship. Instead, each of the 3 is a well-known, honestly-labeled
OHLCV-only APPROXIMATION (`is_proxy: True` on every one of them):
  - Order Flow -> Chaikin-Money-Flow-style close-location-value x volume
    (a standard buying/selling-pressure proxy, not real order-book flow).
  - Volume Profile -> each bar's volume distributed across its own
    High-Low range into price buckets (a standard OHLC-only volume-
    profile approximation, not real trade-level volume-at-price).
  - Institutional Footprint -> rolling volume z-score + range/close-
    position heuristic ("accumulation/distribution/breakout candidate"),
    not confirmed institutional or dark-pool activity.
These 3 are kept as separate, clearly-labeled fields and are NOT blended
into the `confidence` composite below -- their proxy nature makes them
meaningfully less reliable than the 6 primary sub-engines, and folding
them in would silently launder that lower confidence into one number.

Also deliberately NOT rebuilding what already exists elsewhere under a
different name: Multi-Timeframe Engine (get_multi_timeframe_analysis(),
this file), Pattern Recognition Engine (chart_pattern_service.py),
Probability/Regime Engine (direction_probability_service.py +
backend/alpha/regime_detector.py's Bayesian regime), Risk Engine
(engines/risk_engine.py). This module only covers the Level-1 quartet
(Swing/Trend/BOS/CHOCH) plus Liquidity and Volatility as modifiers, and
a Confidence composite tying them together.

WEIGHTS below (Trend 25 / Swing 20 / BOS 20 / CHOCH 15 / Liquidity 10 /
Volatility 10) are a DESIGNED starting point, NOT yet empirically fitted
against services/backtest_service.py -- flagged via
`weights_calibrated: False` in the returned dict rather than silently
presented as validated, matching chart_pattern_service.py's own
PATTERN_CONFIDENCE low/medium/high disclosure convention. Rationale for
the split: Trend+Swing (45% combined) are the structural backbone --
without a real trend and clean swings, nothing else means much. BOS
confirms that backbone is still in force. CHOCH is inherently a
counter-signal to whatever the current read is, so it's weighted
meaningfully but deliberately not enough to whipsaw the whole score on
one single break. Liquidity and Volatility are reliability MODIFIERS
(a fresh liquidity sweep or an extreme/abnormal volatility regime both
make the current read less trustworthy), not primary direction drivers
-- same reason professional discretionary and quant traders alike treat
liquidity pools and vol regime as context filters, not standalone
signals.
"""

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from services.chart_pattern_service import _zigzag_pivots, _atr

WEIGHTS = {
    "trend": 0.25,
    "swing": 0.20,
    "bos": 0.20,
    "choch": 0.15,
    "liquidity": 0.10,
    "volatility": 0.10,
}

MIN_BARS = 20


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, x)))


def _volume_ratio(df: pd.DataFrame, idx: int, window: int = 20) -> Optional[float]:
    """Continuous version of chart_pattern_service._volume_confirms() --
    that helper only returns True/False for a diagnostic string; the
    scoring engines here need the actual ratio to grade breakout/swing
    conviction on a spectrum instead of a hard cutoff."""
    if "Volume" not in df.columns or idx < 0 or idx >= len(df):
        return None
    vol = df["Volume"].astype(float)
    start = max(0, idx - window)
    trailing = vol.iloc[start:idx]
    if trailing.empty:
        return None
    avg = trailing.mean()
    if not avg or avg <= 0:
        return None
    return float(vol.iloc[idx]) / float(avg)


def _swing_engine(pivots: List[Dict], atr_series: pd.Series, df: pd.DataFrame) -> (float, List[Dict]):
    """Scores each of the last few CONFIRMED swings (excludes the final
    still-developing one _zigzag_pivots always appends -- an unconfirmed
    swing hasn't proven anything yet) on three independent, objective
    axes, then averages:
      - magnitude: how big the move was relative to the instrument's own
        ATR at the time (a 0.5x-ATR wiggle is noise; a 4x-ATR move is a
        real swing) -- this is the direct quantified version of "Pivot +
        ATR" from the proposal.
      - volume: was the reversal bar backed by above-average volume
        ("Volume" from the proposal).
      - duration: how many bars the move took -- a swing that completes
        in 1-2 bars is more likely noise than one that develops over
        several ("Time" from the proposal).
    "Distance" from the proposal is folded into magnitude (both describe
    the same real quantity: how far price actually moved).
    """
    confirmed = pivots[:-1] if len(pivots) > 1 else pivots
    recent = confirmed[-6:]
    if len(recent) < 2:
        return 0.0, []

    scores: List[float] = []
    details: List[Dict] = []
    for i in range(1, len(recent)):
        prev, cur = recent[i - 1], recent[i]
        move = abs(cur["price"] - prev["price"])
        bars = max(1, cur["idx"] - prev["idx"])
        atr_idx = min(cur["idx"], len(atr_series) - 1)
        atr_at = float(atr_series.iloc[atr_idx]) if atr_idx >= 0 and len(atr_series) else 0.0
        magnitude_score = _clip((move / atr_at) / 4.0 * 100) if atr_at else 0.0

        vr = _volume_ratio(df, cur["idx"])
        volume_score = _clip((vr / 1.5) * 100) if vr is not None else 50.0

        duration_score = _clip(min(bars, 10) / 10 * 100)

        swing_score = magnitude_score * 0.5 + volume_score * 0.3 + duration_score * 0.2
        scores.append(swing_score)
        details.append({
            "idx": cur["idx"], "kind": cur["kind"], "price": round(cur["price"], 4),
            "score": round(swing_score, 1),
        })

    return (float(np.mean(scores)) if scores else 0.0), details


def _trend_engine(confirmed_highs: List[Dict], confirmed_lows: List[Dict],
                   closes: pd.Series, atr_series: pd.Series) -> float:
    """
      - structural consistency: what fraction of the recent swing-high-
        to-swing-high (and low-to-low) steps kept making higher highs (or
        lower lows) in the SAME direction -- "Higher High Count / Higher
        Low Count" from the proposal, expressed as a 0-100 consistency
        ratio instead of a raw count so it's comparable across tickers.
      - slope: least-squares regression slope of the last 20 closes,
        normalized by ATR so a $500 stock and a $5 stock are compared on
        the same scale ("Slope"/"Momentum" from the proposal).
      - MA position: % distance of last close from its own SMA50 --
        classic trend-strength read, cheap to compute from data already
        fetched.
    ADX is deliberately left out of this first version (flagged as a
    documented future addition, not silently dropped) -- it would need a
    fresh +DI/-DI/DX calculation this codebase doesn't have anywhere yet,
    and the 3 factors above already give a reasonably well-triangulated
    trend read without it.
    """
    def _consistency(seq: List[Dict]) -> float:
        if len(seq) < 3:
            return 50.0  # not enough swings to judge either way -- neutral, not a penalty
        diffs = [seq[i]["price"] - seq[i - 1]["price"] for i in range(1, len(seq))]
        up = sum(1 for d in diffs if d > 0)
        down = sum(1 for d in diffs if d < 0)
        return _clip(max(up, down) / len(diffs) * 100)

    consistency_score = (_consistency(confirmed_highs[-5:]) + _consistency(confirmed_lows[-5:])) / 2

    n = min(20, len(closes))
    if n >= 5:
        xs = np.arange(n, dtype=float)
        ys = closes.iloc[-n:].values.astype(float)
        slope, _intercept = np.polyfit(xs, ys, 1)
        atr_last = float(atr_series.iloc[-1]) if len(atr_series) else 0.0
        slope_norm = abs(slope) / atr_last if atr_last else 0.0
        slope_score = _clip(slope_norm / 0.5 * 100)
    else:
        slope_score = 50.0

    if len(closes) >= 50:
        sma50 = float(closes.rolling(50).mean().iloc[-1])
        dist_pct = abs(float(closes.iloc[-1]) - sma50) / sma50 * 100 if sma50 else 0.0
        ma_score = _clip(dist_pct / 8.0 * 100)
    else:
        ma_score = 50.0

    return consistency_score * 0.40 + slope_score * 0.35 + ma_score * 0.25


def _break_strength(df: pd.DataFrame, level: float, last_close: float,
                     last_high: float, last_low: float, atr_last: float, last_idx: int) -> float:
    """Shared 0-100 confirmation-strength check for BOTH a BOS and a
    CHOCH break -- same underlying question either way: "how convincingly
    did price close beyond this level". Combines:
      - distance beyond the level, in ATR multiples ("Distance" +
        implicitly "ATR" from the proposal)
      - volume ratio on the breakout bar ("Volume")
      - candle body-to-range ratio of the breakout bar ("Body Ratio") --
        a big-bodied breakout candle shows conviction; a thin
        doji-like one closing just past the level is weak evidence.
    "Confirmation Candle" (does price actually hold beyond the level on
    the FOLLOWING bar) is intentionally left for a future iteration --
    this read has to be computable at the moment the break is detected
    (the very last bar), before any "next bar" exists yet.
    """
    if not atr_last:
        return 50.0
    dist_score = _clip((abs(last_close - level) / atr_last) / 1.5 * 100)

    vr = _volume_ratio(df, last_idx)
    vol_score = _clip((vr / 1.5) * 100) if vr is not None else 50.0

    rng = max(last_high - last_low, 1e-9)
    open_px = float(df["Open"].iloc[-1]) if "Open" in df.columns else last_close
    body_score = _clip((abs(last_close - open_px) / rng) * 100)

    return dist_score * 0.40 + vol_score * 0.35 + body_score * 0.25


def _liquidity_engine(highs: List[Dict], lows: List[Dict], last_close: float,
                       last_high: float, last_low: float, atr_last: float) -> (float, List[Dict], Dict):
    """Equal-high/equal-low pool detection ("Equal High"/"Equal Low"/
    "Liquidity Pool" from the proposal) plus a sweep-strength score when
    the latest bar wicks through a level but closes back inside
    ("Sweep"/"Stop Hunt"). Only fires a non-zero score on an ACTUAL
    sweep this bar -- absence of one isn't itself evidence either way."""

    def _equal_cluster(points: List[Dict]) -> Optional[float]:
        recent = points[-5:]
        for i in range(len(recent)):
            for j in range(i + 1, len(recent)):
                pi, pj = recent[i]["price"], recent[j]["price"]
                tol = max(atr_last * 0.25, pi * 0.0015) if atr_last else pi * 0.0015
                if abs(pi - pj) <= tol:
                    return round((pi + pj) / 2, 4)
        return None

    equal_high = _equal_cluster(highs) if len(highs) >= 2 else None
    equal_low = _equal_cluster(lows) if len(lows) >= 2 else None

    events: List[Dict] = []
    score = 0.0
    recent_high = highs[-1]["price"]
    recent_low = lows[-1]["price"]

    if last_high > recent_high and last_close < recent_high:
        wick = last_high - max(last_close, recent_high)
        wick_score = _clip((wick / atr_last) / 0.5 * 100) if atr_last else 50.0
        score = _clip(wick_score * 0.8 + (20.0 if equal_high else 0.0))
        events.append({
            "type": "liquidity_sweep", "direction": "bearish",
            "detail": f"高位插針掃過前高 {round(recent_high, 2)} 後收返落嚟，疑似掃流動性",
        })
    elif last_low < recent_low and last_close > recent_low:
        wick = min(last_close, recent_low) - last_low
        wick_score = _clip((wick / atr_last) / 0.5 * 100) if atr_last else 50.0
        score = _clip(wick_score * 0.8 + (20.0 if equal_low else 0.0))
        events.append({
            "type": "liquidity_sweep", "direction": "bullish",
            "detail": f"低位插針穿過前低 {round(recent_low, 2)} 後收返上去，疑似掃流動性",
        })

    return score, events, {"equal_high": equal_high, "equal_low": equal_low}


def _volatility_engine(atr_series: pd.Series, closes: pd.Series) -> float:
    """Percentile-rank the CURRENT ATR% (ATR / close) against its own
    trailing history, then score how close to the MIDDLE of that
    distribution it sits -- not how high or low. This is deliberately a
    reliability/normality read ("is current volatility a normal regime
    for this instrument, or an extreme one"), not a directional
    bullish/bearish signal: extremely low volatility often means thin/
    illiquid trading (less trustworthy swing detection) and extremely
    high volatility distorts the same ZigZag pivots everything else here
    is built on -- both extremes should DISCOUNT confidence, not boost
    it in either direction, which is why the score peaks at the 50th
    percentile and falls off toward either tail."""
    if atr_series.empty or closes.empty:
        return 50.0
    atr_pct = (atr_series / closes.replace(0, np.nan)) * 100
    window = atr_pct.dropna().iloc[-120:] if len(atr_pct.dropna()) >= 10 else atr_pct.dropna()
    if len(window) < 10:
        return 50.0
    current = float(atr_pct.iloc[-1])
    percentile = float((window < current).sum()) / len(window) * 100
    return _clip(100 - abs(percentile - 50) * 2)


def _order_flow_engine(df: pd.DataFrame, window: int = 20) -> Optional[Dict]:
    """PROXY, not real order flow -- there is no level-2/tick feed in this
    codebase's data sources (yfinance, Alpaca's free IEX feed) to compute
    genuine buy/sell-initiated volume. This instead computes a Chaikin-
    Money-Flow-style read: each bar's Close-Location-Value (where within
    its own High-Low range the bar closed -- near the high implies buying
    pressure, near the low implies selling pressure) times its Volume,
    summed over a trailing window and normalized by total volume in that
    window. A real, honest, widely-used technical-analysis proxy computed
    ENTIRELY from real OHLCV data already fetched -- explicitly flagged
    `is_proxy: True`, never presented as genuine order-book flow.
    Returns a 0-100 score (50 = neutral, >50 = net buying pressure, <50 =
    net selling pressure) plus the raw -100..100 money-flow value.
    """
    if "Volume" not in df.columns or len(df) < 5:
        return None
    n = min(window, len(df))
    sub = df.iloc[-n:]
    high = sub["High"].astype(float)
    low = sub["Low"].astype(float)
    close = sub["Close"].astype(float)
    volume = sub["Volume"].astype(float)
    rng = (high - low).replace(0, np.nan)
    clv = ((close - low) - (high - close)) / rng
    clv = clv.fillna(0.0)
    signed_volume = clv * volume
    total_volume = float(volume.sum())
    if not total_volume:
        return None
    raw_flow = float(signed_volume.sum() / total_volume) * 100  # -100..100
    score = _clip(50 + raw_flow / 2)
    return {"score": round(score, 1), "raw_flow": round(raw_flow, 1), "is_proxy": True}


def _volume_profile_engine(df: pd.DataFrame, lookback: int = 60, bins: int = 20) -> Optional[Dict]:
    """PROXY volume profile -- true volume-at-price needs tick-level trade
    prices this codebase's OHLCV-only sources don't provide. This instead
    distributes EACH bar's already-real total volume across price buckets
    proportional to how much of that bar's own High-Low range falls in
    each bucket (a standard, disclosed approximation used by most retail
    platforms whenever only OHLCV bars are available) -- never presented
    as genuine trade-level volume-at-price (`is_proxy: True`).
    Returns POC (Point of Control -- the bucket with the most estimated
    volume), a Value Area (narrowest set of buckets covering ~70% of
    estimated volume), and where the latest close sits relative to it.
    """
    if "Volume" not in df.columns or len(df) < 10:
        return None
    n = min(lookback, len(df))
    sub = df.iloc[-n:]
    lo = float(sub["Low"].min())
    hi = float(sub["High"].max())
    if hi <= lo:
        return None
    edges = np.linspace(lo, hi, bins + 1)
    vol_per_bin = np.zeros(bins)
    for _, row in sub.iterrows():
        b_lo, b_hi, b_vol = float(row["Low"]), float(row["High"]), float(row["Volume"])
        if b_hi <= b_lo or not b_vol:
            continue
        overlap_lo = np.clip(edges[:-1], b_lo, b_hi)
        overlap_hi = np.clip(edges[1:], b_lo, b_hi)
        overlap = np.maximum(0.0, overlap_hi - overlap_lo)
        total_overlap = float(overlap.sum())
        if total_overlap <= 0:
            continue
        vol_per_bin += (overlap / total_overlap) * b_vol

    if vol_per_bin.sum() <= 0:
        return None

    poc_idx = int(np.argmax(vol_per_bin))
    poc_price = float((edges[poc_idx] + edges[poc_idx + 1]) / 2)

    order = np.argsort(vol_per_bin)[::-1]
    target = vol_per_bin.sum() * 0.70
    covered = 0.0
    chosen: List[int] = []
    for idx in order:
        chosen.append(int(idx))
        covered += vol_per_bin[idx]
        if covered >= target:
            break
    lo_bin, hi_bin = min(chosen), max(chosen)
    value_area_low = float(edges[lo_bin])
    value_area_high = float(edges[hi_bin + 1])

    last_close = float(df["Close"].iloc[-1])
    if last_close > value_area_high:
        position = "above_value_area"
    elif last_close < value_area_low:
        position = "below_value_area"
    else:
        position = "inside_value_area"

    return {
        "poc": round(poc_price, 4),
        "value_area_high": round(value_area_high, 4),
        "value_area_low": round(value_area_low, 4),
        "position": position,
        "is_proxy": True,
    }


def _institutional_footprint_engine(df: pd.DataFrame, window: int = 20) -> Optional[Dict]:
    """PROXY, not confirmed institutional/dark-pool activity -- genuine
    footprint detection needs block-trade prints or dark-pool data no free
    source here provides. This instead flags STATISTICALLY UNUSUAL volume
    bars (a z-score against the trailing window) and classifies them by
    how much the bar's range expanded: unusual volume + a NARROW range
    (relative to ATR) suggests size being absorbed quietly ("accumulation/
    distribution candidate" -- large orders filled without moving price
    much); unusual volume + a WIDE range suggests size pushing price
    aggressively instead ("breakout candidate"). A well-known
    discretionary/retail heuristic, explicitly labeled a CANDIDATE, never
    asserted as confirmed institutional activity (`is_proxy: True`).
    """
    if "Volume" not in df.columns or len(df) < window + 5:
        return None
    vol = df["Volume"].astype(float)
    trailing = vol.iloc[-(window + 1):-1]
    if trailing.empty:
        return None
    mean, std = float(trailing.mean()), float(trailing.std())
    if not std or std != std:
        return None
    last_vol = float(vol.iloc[-1])
    z = (last_vol - mean) / std

    last_high = float(df["High"].iloc[-1])
    last_low = float(df["Low"].iloc[-1])
    last_close = float(df["Close"].iloc[-1])
    rng = max(last_high - last_low, 1e-9)

    atr_series = _atr(df)
    atr_last = float(atr_series.iloc[-1]) if len(atr_series) else 0.0
    range_ratio = (rng / atr_last) if atr_last else 1.0

    score = _clip(z / 3.0 * 100) if z > 0 else 0.0
    close_pos = (last_close - last_low) / rng

    if z <= 1.0:
        candidate = None
        direction = None
    elif range_ratio < 0.8:
        candidate = "accumulation" if close_pos >= 0.5 else "distribution"
        direction = "bullish" if candidate == "accumulation" else "bearish"
    else:
        candidate = "breakout"
        direction = "bullish" if close_pos >= 0.5 else "bearish"

    return {
        "score": round(score, 1),
        "volume_zscore": round(z, 2),
        "candidate": candidate,
        "direction": direction,
        "is_proxy": True,
    }


def compute_market_structure(df: pd.DataFrame) -> Optional[Dict]:
    """
    Main entry point -- replaces the old TechnicalAnalysisService.
    _market_structure() call site (that static method is left in the
    class below, unused, rather than deleted, in case anything else ever
    needs the exact old boolean-only shape back).

    Returns None (not fabricated events/scores) when there isn't enough
    real swing/bar data to classify -- same honesty posture as the code
    it replaces.
    """
    if df is None or df.empty or len(df) < MIN_BARS:
        return None

    pivots = _zigzag_pivots(df)
    highs = [p for p in pivots if p["kind"] == "high"]
    lows = [p for p in pivots if p["kind"] == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return None

    atr_series = _atr(df)
    closes = df["Close"].astype(float)
    last_idx = len(df) - 1
    last_close = float(closes.iloc[-1])
    last_high = float(df["High"].iloc[-1])
    last_low = float(df["Low"].iloc[-1])
    atr_last = float(atr_series.iloc[-1]) if len(atr_series) else 0.0

    recent_high, prior_high = highs[-1]["price"], highs[-2]["price"]
    recent_low, prior_low = lows[-1]["price"], lows[-2]["price"]

    if recent_high > prior_high and recent_low > prior_low:
        prior_structure = "uptrend"
    elif recent_high < prior_high and recent_low < prior_low:
        prior_structure = "downtrend"
    else:
        prior_structure = "mixed"

    events: List[Dict] = []
    bos_score = 0.0
    choch_score = 0.0

    if prior_structure == "uptrend" and last_close > recent_high:
        bos_score = _break_strength(df, recent_high, last_close, last_high, last_low, atr_last, last_idx)
        events.append({
            "type": "BOS", "direction": "bullish",
            "detail": f"價格企穩突破前高 {round(recent_high, 2)}，確認上升結構延續",
        })
    elif prior_structure == "downtrend" and last_close < recent_low:
        bos_score = _break_strength(df, recent_low, last_close, last_high, last_low, atr_last, last_idx)
        events.append({
            "type": "BOS", "direction": "bearish",
            "detail": f"價格企穩跌穿前低 {round(recent_low, 2)}，確認下降結構延續",
        })

    if prior_structure == "downtrend" and last_close > recent_high:
        choch_score = _break_strength(df, recent_high, last_close, last_high, last_low, atr_last, last_idx)
        events.append({
            "type": "CHOCH", "direction": "bullish",
            "detail": f"價格突破前高 {round(recent_high, 2)}，下降結構出現轉勢跡象",
        })
    elif prior_structure == "uptrend" and last_close < recent_low:
        choch_score = _break_strength(df, recent_low, last_close, last_high, last_low, atr_last, last_idx)
        events.append({
            "type": "CHOCH", "direction": "bearish",
            "detail": f"價格跌穿前低 {round(recent_low, 2)}，上升結構出現轉勢跡象",
        })

    liquidity_score, liquidity_events, liquidity_pools = _liquidity_engine(
        highs, lows, last_close, last_high, last_low, atr_last
    )
    events.extend(liquidity_events)

    swing_quality, swing_details = _swing_engine(pivots, atr_series, df)
    trend_score = _trend_engine(highs[:-1] if len(highs) > 1 else highs,
                                 lows[:-1] if len(lows) > 1 else lows, closes, atr_series)
    volatility_score = _volatility_engine(atr_series, closes)

    # PROXY-only engines (see module docstring) -- informational, not
    # blended into `confidence` below.
    order_flow = _order_flow_engine(df)
    volume_profile = _volume_profile_engine(df)
    institutional_footprint = _institutional_footprint_engine(df)

    # "No event this bar" defaults to a neutral 50 for BOS/CHOCH/Liquidity
    # -- most bars are mid-range (no break at all), and that absence is
    # simply "no fresh evidence either way", not itself negative or
    # positive. CHOCH is inverted (100 - score) because a STRONG CHOCH is
    # bad news for confidence in whatever structure is currently labeled
    # -- it's a genuine counter-signal, not a confirmation.
    bos_component = bos_score if bos_score else 50.0
    choch_component = (100 - choch_score) if choch_score else 50.0
    liquidity_component = (100 - liquidity_score) if liquidity_score else 50.0

    confidence = (
        trend_score * WEIGHTS["trend"]
        + swing_quality * WEIGHTS["swing"]
        + bos_component * WEIGHTS["bos"]
        + choch_component * WEIGHTS["choch"]
        + liquidity_component * WEIGHTS["liquidity"]
        + volatility_score * WEIGHTS["volatility"]
    )

    return {
        # ---- unchanged fields (existing frontend consumer contract) ----
        "prior_structure": prior_structure,
        "recent_swing_high": round(recent_high, 2),
        "recent_swing_low": round(recent_low, 2),
        "events": events,
        # ---- new V2 quantified fields ----
        "trend_score": round(trend_score, 1),
        "swing_quality": round(swing_quality, 1),
        "bos_score": round(bos_score, 1),
        "choch_score": round(choch_score, 1),
        "liquidity_score": round(liquidity_score, 1),
        "volatility_score": round(volatility_score, 1),
        "confidence": round(_clip(confidence), 1),
        "weights": WEIGHTS,
        "weights_calibrated": False,
        "liquidity_pools": liquidity_pools,
        "swing_details": swing_details,
        # ---- proxy-only fields (see module docstring), not part of `confidence` ----
        "order_flow": order_flow,
        "volume_profile": volume_profile,
        "institutional_footprint": institutional_footprint,
    }
