"""
Chart Pattern Service — rule-based geometric chart-pattern detection from
REAL OHLC swing-point data (the ticker-search flow in chart-analysis.html,
"搜尋代號（免上傳）").

This is a DIFFERENT code path from api/chart_analysis.py's AI-vision
pattern recognition (used only for uploaded screenshots, see that file's
docstring / services/technical_analysis_service.py's module docstring).
That AI-vision path is still the only option when there's no ticker (a
raw uploaded image with no real price series to compute from). This
module instead runs deterministic geometry on the SAME real swing-point
data services/technical_analysis_service.py already computes for every
ticker search (support/resistance, Market Structure BOS/CHOCH) — no AI
call, no image, no extra network fetch.

Honesty policy (matches Market Structure Engine's own docstring: "Returns
None ... not fabricated events ... not enough structure to classify"):
every verdict here is a deterministic threshold check on real price
geometry, not a guess. Patterns with well-established, mostly-objective
geometric definitions (double top/bottom, head & shoulders, triangle,
channel, rectangle, broadening, gap, island reversal, 0.618 retracement)
get a plain 可能/不可能 verdict. Patterns that are inherently more
subjective even among professional chartists (cup & handle, diamond, ABC
correction wave, flag, pennant) are still computed from real geometry
using the same rules, but this is disclosed to the caller via
PATTERN_CONFIDENCE below rather than silently presented as being as
reliable as the rest — chart-analysis.html surfaces this as a caveat next
to the Pattern Details block.

All thresholds below are fixed, documented constants — nothing here is
randomised or fitted per-request, so results are fully reproducible for
the same OHLC input.

v2 note (pivot/slope/volume rigor pass): swing points are now found with
an ATR-adaptive ZigZag (a pivot confirms once price reverses by
max(ATR*mult, price*min_pct) from the last tracked extreme) instead of a
fixed 5-bar fractal window -- this scales the "how big a wiggle counts"
threshold to the instrument's own recent volatility, so a quiet utility
stock and a volatile crypto pair each get a sensibly-sized pivot instead
of one flat percentage rule for both (see ZigZag indicator literature).
Shape-fitting for triangle/channel/rectangle/broadening now uses a proper
least-squares regression slope (numpy.polyfit) across the recent swings
rather than an average of consecutive point-to-point diffs, so a single
outlier swing can no longer dominate the fitted trendline. Breakout-
dependent checks (double top/bottom, H&S top/bottom, breakout retest,
gap, island) also now note whether the relevant bar's volume confirms
(>=1.25x its trailing 20-bar average) per Bulkowski-style breakout
statistics, appended to the diagnostic `detail` string. Per deliberate
design choice, none of this raises the bar for the top-level 可能/不可能
verdict itself (still a shape-only check) -- it only makes the underlying
swing/slope math more robust and enriches the diagnostic detail/marker
text, so existing detection sensitivity is preserved.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Verdicts use the exact same two literal strings the AI-vision upload
# flow already returns for these same p_* keys (see api/chart_analysis.py's
# vision-prompt JSON schema) -- chart-analysis.html's frontend displays
# them as-is in every language (never translated, by existing design), so
# reusing the identical literals means zero frontend/i18n changes needed.
POSSIBLE = "可能"
NOT_POSSIBLE = "不可能"

# Disclosed to the frontend so it can show a caveat only where it's
# warranted -- "medium"/"high" confidence patterns have fairly objective,
# widely-agreed geometric definitions; "low" ones are still real-geometry
# checks but the underlying chart pattern itself is inherently more
# judgment-call-y even for a human chartist looking at the same chart.
PATTERN_CONFIDENCE = {
    "p_double_top": "medium",
    "p_double_bottom": "medium",
    "p_head_shoulder_top": "medium",
    "p_head_shoulder_bottom": "medium",
    "p_triangle": "medium",
    "p_breakback": "medium",
    "p_0618": "high",
    "p_flag": "low",
    "p_pennant": "low",
    "p_channel": "medium",
    "p_rectangle": "medium",
    "p_cup_handle": "low",
    "p_diamond": "low",
    "p_broadening": "medium",
    "p_abc": "low",
    "p_gap": "high",
    "p_island": "medium",
}

# How far back (in bars) a pattern's most recent point may sit and still
# count as "current" rather than stale ancient history. Two windows:
# LOOKBACK_SWING for the multi-swing shape patterns (double top/H&S/
# triangle/channel/rectangle/broadening — need several swings to compare,
# so a longer window), LOOKBACK_SHORT for inherently short-lived
# continuation patterns (flag/pennant/gap/island — by definition recent).
LOOKBACK_SWING = 80
LOOKBACK_SHORT = 20


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Standard Wilder-style True Range, smoothed with a simple rolling
    mean (min_periods=1 so the series has no leading NaNs -- the ZigZag
    below needs a usable threshold from the very first bar)."""
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    prev_close = close.shift(1)
    prev_close.iloc[0] = close.iloc[0]  # first bar: no prior close, so TR = high-low only
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def _zigzag_pivots(
    df: pd.DataFrame, atr_period: int = 14, atr_mult: float = 1.5, min_pct: float = 0.02
) -> List[Dict]:
    """
    Chronological list of {time, idx, price, kind} swing pivots -- kind is
    "high" or "low". Single-pass ATR-adaptive ZigZag: track the running
    price extreme since the last confirmed pivot, and confirm a new pivot
    the moment price reverses away from that extreme by at least
    max(ATR(atr_period)[i] * atr_mult, price[i] * min_pct).

    This replaces the earlier fixed 5-bar-window fractal detector, which
    used one flat percentage-style rule for every instrument regardless of
    its own volatility -- too loose for a volatile name (misses real
    pivots, or merges several into one) and too strict for a quiet one
    (fires on ordinary noise). Scaling the threshold to the instrument's
    own recent ATR (the standard ZigZag-indicator approach) fixes both. A
    min_pct floor guards against the odd case where ATR is close to zero
    (e.g. a long flat stretch) from producing near-continuous pivots.

    The final in-progress swing (the extreme reached since the last
    confirmed pivot, not yet reversed far enough to confirm) is appended
    too -- pattern checks below need to reason about "the current/latest
    swing", which is often still developing rather than already confirmed.
    """
    n = len(df)
    if n < 3:
        return []

    atr = _atr(df, atr_period)
    highs = df["High"].astype(float)
    lows = df["Low"].astype(float)
    closes = df["Close"].astype(float)

    def _threshold(i: int) -> float:
        return max(float(atr.iloc[i]) * atr_mult, float(closes.iloc[i]) * min_pct)

    pivots: List[Dict] = []
    trend: Optional[str] = None  # "up" (tracking towards a high) or "down"
    ext_idx = 0
    ext_high = float(highs.iloc[0])
    ext_low = float(lows.iloc[0])

    def _mk(idx: int, price: float, kind: str) -> Dict:
        return {"time": int(df.index[idx].timestamp()), "idx": idx, "price": round(price, 6), "kind": kind}

    for i in range(1, n):
        h, l = float(highs.iloc[i]), float(lows.iloc[i])
        thr = _threshold(i)

        if trend is None:
            # Still establishing initial direction from the opening range.
            if h - ext_low >= thr:
                pivots.append(_mk(ext_idx, ext_low, "low"))
                trend = "up"
                ext_high, ext_idx = h, i
            elif ext_high - l >= thr:
                pivots.append(_mk(ext_idx, ext_high, "high"))
                trend = "down"
                ext_low, ext_idx = l, i
            else:
                if h > ext_high:
                    ext_high = h
                if l < ext_low:
                    ext_low = l
            continue

        if trend == "up":
            if h > ext_high:
                ext_high, ext_idx = h, i
            elif ext_high - l >= thr:
                pivots.append(_mk(ext_idx, ext_high, "high"))
                trend = "down"
                ext_low, ext_idx = l, i
        else:  # trend == "down"
            if l < ext_low:
                ext_low, ext_idx = l, i
            elif h - ext_low >= thr:
                pivots.append(_mk(ext_idx, ext_low, "low"))
                trend = "up"
                ext_high, ext_idx = h, i

    # Append the still-developing final swing so callers can see "the
    # latest swing high/low" even when it hasn't reversed far enough to
    # confirm yet (mirrors how a chartist reads an in-progress swing).
    if trend == "up":
        pivots.append(_mk(ext_idx, ext_high, "high"))
    elif trend == "down":
        pivots.append(_mk(ext_idx, ext_low, "low"))

    pivots.sort(key=lambda p: p["idx"])
    return pivots


def _pivots(df: pd.DataFrame, atr_period: int = 14, atr_mult: float = 1.5, min_pct: float = 0.02) -> List[Dict]:
    """Thin, name-stable wrapper around _zigzag_pivots so every existing
    call site below (and detect_patterns()) picks up the ATR-adaptive
    ZigZag without any other code needing to change."""
    return _zigzag_pivots(df, atr_period=atr_period, atr_mult=atr_mult, min_pct=min_pct)


def _pt(p: Dict) -> Dict:
    return {"time": p["time"], "price": round(p["price"], 4)}


def _recent(pivots: List[Dict], kind: str, n_bars: int, last_idx: int, count: Optional[int] = None) -> List[Dict]:
    pts = [p for p in pivots if p["kind"] == kind and p["idx"] >= last_idx - n_bars]
    return pts[-count:] if count else pts


def _slope(points: List[Dict]) -> float:
    """Least-squares linear-regression slope (price per pivot-step) across
    the given points, via numpy.polyfit. Replaces the earlier average-of-
    consecutive-diffs approach, which let a single outlier swing skew the
    whole read (e.g. 3 flat pivots + 1 spike averaged to "sloping" even
    though the overall trendline is flat) -- a proper fit uses every point
    at once. Same call signature/units as before, so every existing caller
    (triangle/channel/rectangle/broadening/flag-pennant/diamond) is a
    drop-in, no threshold retuning needed."""
    if len(points) < 2:
        return 0.0
    xs = np.arange(len(points), dtype=float)
    ys = np.array([p["price"] for p in points], dtype=float)
    slope, _intercept = np.polyfit(xs, ys, 1)
    return float(slope)


def _volume_confirms(df: pd.DataFrame, idx: int, mult: float = 1.25, window: int = 20) -> Optional[bool]:
    """Bulkowski-style breakout volume confirmation: does the bar at `idx`
    trade at least `mult`x its trailing `window`-bar average volume?
    Returns None (not True/False) when it can't be judged at all -- no
    Volume column, not enough history before idx, or a zero/garbage
    trailing average -- so callers can honestly say "unknown" rather than
    silently treating unknown as a fail. This is diagnostic-only: it never
    changes a verdict, only enriches the `detail` string (deliberately, to
    avoid re-introducing the earlier "feature is unusable" complaint from
    tightening shape-only triggers into breakout+volume-gated ones)."""
    if "Volume" not in df.columns or idx <= 0 or idx >= len(df):
        return None
    vol = df["Volume"].astype(float)
    start = max(0, idx - window)
    trailing = vol.iloc[start:idx]
    if trailing.empty:
        return None
    avg = trailing.mean()
    if not avg or avg <= 0:
        return None
    return bool(vol.iloc[idx] >= avg * mult)


def _vol_note(df: pd.DataFrame, idx: int) -> str:
    """Human-readable (Chinese) fragment describing volume confirmation at
    bar `idx`, for appending to a pattern's `detail` string."""
    confirmed = _volume_confirms(df, idx)
    if confirmed is None:
        return "，成交量數據不足以判斷"
    return "，成交量放大配合" if confirmed else "，成交量未見放大配合"


def _empty(reason: str) -> Tuple[str, str, List[Dict]]:
    return NOT_POSSIBLE, reason, []


# ---- individual pattern checks ------------------------------------------
# Each returns (verdict, detail_zh, points) where points is the list of
# {time, price} chart coordinates worth drawing when verdict == POSSIBLE
# (empty otherwise). detail_zh is diagnostic-only (not shown in the
# current text UI, kept for the on-chart tooltip/label built in the
# chart-drawing phase and for debugging).

def _double_top(df: pd.DataFrame, highs: List[Dict], lows: List[Dict], last_idx: int) -> Tuple[str, str, List[Dict]]:
    if len(highs) < 2:
        return _empty("swing high 少於2個")
    h2, h1 = highs[-1], highs[-2]
    if abs(h2["price"] - h1["price"]) / h1["price"] > 0.03:
        return _empty("兩個高位相差超過3%")
    between = [l for l in lows if h1["idx"] < l["idx"] < h2["idx"]]
    if not between:
        return _empty("兩個高位之間冇明顯回落")
    trough = min(between, key=lambda l: l["price"])
    if trough["price"] > min(h1["price"], h2["price"]) * 0.97:
        return _empty("中間回落幅度不足3%")
    detail = (
        f"高位 {round(h1['price'],2)}/{round(h2['price'],2)} 相差"
        f"{round(abs(h2['price']-h1['price'])/h1['price']*100,1)}%，中間拉回至{round(trough['price'],2)}"
        + _vol_note(df, h2["idx"])
    )
    return POSSIBLE, detail, [_pt(h1), _pt(trough), _pt(h2)]


def _double_bottom(df: pd.DataFrame, highs: List[Dict], lows: List[Dict], last_idx: int) -> Tuple[str, str, List[Dict]]:
    if len(lows) < 2:
        return _empty("swing low 少於2個")
    l2, l1 = lows[-1], lows[-2]
    if abs(l2["price"] - l1["price"]) / l1["price"] > 0.03:
        return _empty("兩個低位相差超過3%")
    between = [h for h in highs if l1["idx"] < h["idx"] < l2["idx"]]
    if not between:
        return _empty("兩個低位之間冇明顯反彈")
    peak = max(between, key=lambda h: h["price"])
    if peak["price"] < max(l1["price"], l2["price"]) * 1.03:
        return _empty("中間反彈幅度不足3%")
    detail = (
        f"低位 {round(l1['price'],2)}/{round(l2['price'],2)} 相差"
        f"{round(abs(l2['price']-l1['price'])/l1['price']*100,1)}%，中間反彈至{round(peak['price'],2)}"
        + _vol_note(df, l2["idx"])
    )
    return POSSIBLE, detail, [_pt(l1), _pt(peak), _pt(l2)]


def _head_shoulder_top(df: pd.DataFrame, highs: List[Dict], lows: List[Dict], last_idx: int) -> Tuple[str, str, List[Dict]]:
    if len(highs) < 3:
        return _empty("swing high 少於3個")
    l_sh, head, r_sh = highs[-3], highs[-2], highs[-1]
    if not (head["price"] > l_sh["price"] * 1.02 and head["price"] > r_sh["price"] * 1.02):
        return _empty("中間高位未夠明顯高過兩側")
    if abs(l_sh["price"] - r_sh["price"]) / l_sh["price"] > 0.05:
        return _empty("兩個肩部相差超過5%")
    neckline = [l for l in lows if l_sh["idx"] < l["idx"] < r_sh["idx"]]
    if len(neckline) < 2:
        return _empty("兩個肩部之間頸線點不足")
    detail = f"左肩{round(l_sh['price'],2)}／頭{round(head['price'],2)}／右肩{round(r_sh['price'],2)}" + _vol_note(df, r_sh["idx"])
    return POSSIBLE, detail, [_pt(l_sh)] + [_pt(n) for n in neckline] + [_pt(head), _pt(r_sh)]


def _head_shoulder_bottom(df: pd.DataFrame, highs: List[Dict], lows: List[Dict], last_idx: int) -> Tuple[str, str, List[Dict]]:
    if len(lows) < 3:
        return _empty("swing low 少於3個")
    l_sh, head, r_sh = lows[-3], lows[-2], lows[-1]
    if not (head["price"] < l_sh["price"] * 0.98 and head["price"] < r_sh["price"] * 0.98):
        return _empty("中間低位未夠明顯低過兩側")
    if abs(l_sh["price"] - r_sh["price"]) / l_sh["price"] > 0.05:
        return _empty("兩個肩部相差超過5%")
    neckline = [h for h in highs if l_sh["idx"] < h["idx"] < r_sh["idx"]]
    if len(neckline) < 2:
        return _empty("兩個肩部之間頸線點不足")
    detail = f"左肩{round(l_sh['price'],2)}／頭{round(head['price'],2)}／右肩{round(r_sh['price'],2)}" + _vol_note(df, r_sh["idx"])
    return POSSIBLE, detail, [_pt(l_sh)] + [_pt(n) for n in neckline] + [_pt(head), _pt(r_sh)]


def _range_shape(highs: List[Dict], lows: List[Dict], count: int = 3) -> Optional[Tuple[float, float, List[Dict]]]:
    """Shared helper for triangle/channel/rectangle/broadening: needs at
    least `count` recent swing highs and lows, returns (high_slope,
    low_slope, points_used) or None if there isn't enough shape data."""
    if len(highs) < count or len(lows) < count:
        return None
    hh = highs[-count:]
    ll = lows[-count:]
    return _slope(hh), _slope(ll), [_pt(p) for p in hh] + [_pt(p) for p in ll]


def _triangle(highs: List[Dict], lows: List[Dict]) -> Tuple[str, str, List[Dict]]:
    shape = _range_shape(highs, lows)
    if not shape:
        return _empty("高低位數量不足")
    hs, ls, pts = shape
    ref = (highs[-1]["price"] + lows[-1]["price"]) / 2
    eps = ref * 0.003
    converging = (hs < -eps or abs(hs) <= eps) and (ls > eps or abs(ls) <= eps) and not (abs(hs) <= eps and abs(ls) <= eps)
    if not converging:
        return _empty("高低位斜率唔符合收斂形態")
    return POSSIBLE, "高位走平/回落，低位走平/抬升，波幅收窄", pts


def _channel(highs: List[Dict], lows: List[Dict]) -> Tuple[str, str, List[Dict]]:
    shape = _range_shape(highs, lows)
    if not shape:
        return _empty("高低位數量不足")
    hs, ls, pts = shape
    ref = (highs[-1]["price"] + lows[-1]["price"]) / 2
    eps = ref * 0.003
    if abs(hs) <= eps and abs(ls) <= eps:
        return _empty("屬於矩形整理而非通道")
    same_dir = (hs > eps and ls > eps) or (hs < -eps and ls < -eps)
    if not same_dir:
        return _empty("高低位方向唔一致")
    if abs(hs - ls) > max(abs(hs), abs(ls)) * 0.6:
        return _empty("高低位斜率相差太遠，唔算平行")
    return POSSIBLE, "高低位同向平行移動", pts


def _rectangle(highs: List[Dict], lows: List[Dict]) -> Tuple[str, str, List[Dict]]:
    shape = _range_shape(highs, lows)
    if not shape:
        return _empty("高低位數量不足")
    hs, ls, pts = shape
    ref = (highs[-1]["price"] + lows[-1]["price"]) / 2
    eps = ref * 0.004
    if abs(hs) <= eps and abs(ls) <= eps:
        return POSSIBLE, "高低位大致走平，區間橫行", pts
    return _empty("高低位並非走平")


def _broadening(highs: List[Dict], lows: List[Dict]) -> Tuple[str, str, List[Dict]]:
    shape = _range_shape(highs, lows)
    if not shape:
        return _empty("高低位數量不足")
    hs, ls, pts = shape
    ref = (highs[-1]["price"] + lows[-1]["price"]) / 2
    eps = ref * 0.003
    if hs > eps and ls < -eps:
        return POSSIBLE, "高位持續抬升，低位持續下降，波幅擴大", pts
    return _empty("高低位唔符合擴散形態")


def _breakback(df: pd.DataFrame, pivots: List[Dict], closes: pd.Series, last_idx: int) -> Tuple[str, str, List[Dict]]:
    """Breakout retest: price broke above a prior swing-high resistance and
    has since pulled back close to (without re-crossing below) that level."""
    highs = [p for p in pivots if p["kind"] == "high" and p["idx"] < last_idx - 3]
    if not highs:
        return _empty("冇早前高位可比較")
    broken = max(highs, key=lambda h: h["price"])
    last_close = float(closes.iloc[-1])
    if last_close <= broken["price"]:
        return _empty("現價未突破前高")
    recent_low = float(closes.iloc[-5:].min()) if len(closes) >= 5 else last_close
    if recent_low < broken["price"] * 0.98:
        return _empty("回測時已明顯跌穿突破位")
    dist = abs(last_close - broken["price"]) / broken["price"]
    if dist > 0.03:
        return _empty("現價離突破位太遠，未算回測")
    # Volume confirmation is judged at the bar where price first cleared
    # the broken level (a genuine breakout should show above-average
    # volume there), not at the current retest bar.
    breakout_idx = next((p["idx"] for p in pivots if p["idx"] > broken["idx"]), last_idx)
    detail = f"突破前高{round(broken['price'],2)}後拉回測試" + _vol_note(df, breakout_idx)
    return POSSIBLE, detail, [_pt(broken)]


def _fib_0618(highs: List[Dict], lows: List[Dict], closes: pd.Series) -> Tuple[str, str, List[Dict]]:
    if not highs or not lows:
        return _empty("冇足夠swing點計波幅")
    swing_high = max(p["price"] for p in highs)
    swing_low = min(p["price"] for p in lows)
    if swing_high <= swing_low:
        return _empty("波幅無效")
    level = swing_high - (swing_high - swing_low) * 0.618
    last_close = float(closes.iloc[-1])
    if abs(last_close - level) / level <= 0.015:
        return POSSIBLE, f"現價貼近0.618回調位{round(level,2)}", []
    return _empty("現價未貼近0.618回調位")


def _flag_pennant(df: pd.DataFrame, highs: List[Dict], lows: List[Dict], last_idx: int) -> Tuple[str, str, str, List[Dict]]:
    """Shared impulse-then-consolidation check for flag vs pennant.
    Returns (flag_verdict, pennant_verdict, detail, points)."""
    closes = df["Close"]
    n = len(closes)
    impulse_bars = min(15, n - 1)
    consolidation_bars = min(6, n - 1)
    if n < impulse_bars + consolidation_bars + 1:
        return NOT_POSSIBLE, NOT_POSSIBLE, "數據不足", []
    pre = closes.iloc[-(impulse_bars + consolidation_bars):-consolidation_bars]
    impulse_pct = (pre.iloc[-1] - pre.iloc[0]) / pre.iloc[0] if pre.iloc[0] else 0
    if abs(impulse_pct) < 0.06:
        return NOT_POSSIBLE, NOT_POSSIBLE, "冇明顯衝浪段", []
    recent_highs = [p for p in highs if p["idx"] >= last_idx - consolidation_bars]
    recent_lows = [p for p in lows if p["idx"] >= last_idx - consolidation_bars]
    tail = df.iloc[-consolidation_bars:]
    ref = float(closes.iloc[-1])
    eps = ref * 0.004
    if len(recent_highs) >= 2 and len(recent_lows) >= 2:
        hs, ls = _slope(recent_highs), _slope(recent_lows)
        converging = (hs < -eps and ls > -eps) or (ls > eps and hs < eps)
        pts = [_pt(p) for p in recent_highs] + [_pt(p) for p in recent_lows]
        if converging:
            return NOT_POSSIBLE, POSSIBLE, f"衝浪{round(impulse_pct*100,1)}%後短暫收斂整理", pts
        return POSSIBLE, NOT_POSSIBLE, f"衝浪{round(impulse_pct*100,1)}%後短暫平行整理", pts
    # Not enough swing points inside the short window to judge shape --
    # fall back to plain range compression as a (weaker) flag signal only.
    consolidation_range = (tail["High"].max() - tail["Low"].min()) / ref
    if consolidation_range < abs(impulse_pct) * 0.5:
        return POSSIBLE, NOT_POSSIBLE, f"衝浪{round(impulse_pct*100,1)}%後波幅明顯收窄", []
    return NOT_POSSIBLE, NOT_POSSIBLE, "整理段未夠收斂", []


def _cup_handle(df: pd.DataFrame, last_idx: int) -> Tuple[str, str, List[Dict]]:
    """Low-confidence heuristic: rounded U-shape recovery back near the
    starting level, then a small pullback (handle) in the last few bars."""
    closes = df["Close"]
    n = len(closes)
    window = min(60, n - 1)
    if window < 20:
        return _empty("數據不足")
    seg = closes.iloc[-window:]
    start, low_point, end = seg.iloc[0], seg.min(), seg.iloc[-6] if len(seg) > 6 else seg.iloc[-1]
    low_idx = seg.values.argmin()
    if not (0.15 * window < low_idx < 0.85 * window):
        return _empty("低點唔喺中段，唔似U形")
    if low_point > start * 0.92:
        return _empty("下跌深度不足，唔似杯形")
    if end < start * 0.95:
        return _empty("未回升返近起點水平")
    handle = closes.iloc[-6:]
    handle_dip = (handle.max() - handle.min()) / handle.max() if len(handle) > 1 else 0
    if handle_dip < 0.01 or handle_dip > 0.08:
        return _empty("手柄段拉回幅度唔合理")
    return POSSIBLE, "U形回升後見小幅拉回（手柄）", []


def _diamond(highs: List[Dict], lows: List[Dict], last_idx: int) -> Tuple[str, str, List[Dict]]:
    """Low-confidence heuristic: broadening in the earlier half of the
    recent swing window, then narrowing (triangle-like) in the later half."""
    if len(highs) < 4 or len(lows) < 4:
        return _empty("高低位數量不足")
    h_first, h_last = highs[-4:-2], highs[-2:]
    l_first, l_last = lows[-4:-2], lows[-2:]
    broaden_hs, broaden_ls = _slope(h_first), _slope(l_first)
    narrow_hs, narrow_ls = _slope(h_last), _slope(l_last)
    ref = (highs[-1]["price"] + lows[-1]["price"]) / 2
    eps = ref * 0.003
    broadened = broaden_hs > eps and broaden_ls < -eps
    narrowed = narrow_hs < eps and narrow_ls > -eps
    if broadened and narrowed:
        pts = [_pt(p) for p in h_first + h_last + l_first + l_last]
        return POSSIBLE, "先擴散後收斂，形似菱形", pts
    return _empty("未見「先擴散後收斂」形態")


def _abc(highs: List[Dict], lows: List[Dict], last_idx: int) -> Tuple[str, str, List[Dict]]:
    """Low-confidence heuristic: 3-swing A-B-C correction -- B retraces
    38.2%-61.8% of A, C continues beyond B in A's direction."""
    all_pivots = sorted(highs + lows, key=lambda p: p["idx"])
    recent = [p for p in all_pivots if p["idx"] >= last_idx - LOOKBACK_SWING]
    if len(recent) < 4:
        return _empty("swing點不足以數ABC浪")
    a0, a1, b1, c1 = recent[-4], recent[-3], recent[-2], recent[-1]
    leg_a = a1["price"] - a0["price"]
    leg_b = b1["price"] - a1["price"]
    leg_c = c1["price"] - b1["price"]
    if leg_a == 0 or (leg_a > 0) == (leg_b > 0):
        return _empty("B浪未見反向回撤")
    retrace = abs(leg_b) / abs(leg_a)
    if not (0.382 <= retrace <= 0.786):
        return _empty("B浪回撤比例唔喺常見範圍")
    if (leg_c > 0) != (leg_a > 0):
        return _empty("C浪方向同A浪唔一致")
    return POSSIBLE, f"B浪回撤A浪{round(retrace*100,0)}%後，C浪延續原方向", [_pt(a0), _pt(a1), _pt(b1), _pt(c1)]


def _gap(df: pd.DataFrame, lookback: int = 15) -> Tuple[str, str, List[Dict]]:
    n = len(df)
    start = max(1, n - lookback)
    for i in range(n - 1, start - 1, -1):
        prev_high, prev_low = float(df["High"].iloc[i - 1]), float(df["Low"].iloc[i - 1])
        cur_high, cur_low = float(df["High"].iloc[i]), float(df["Low"].iloc[i])
        ref = float(df["Close"].iloc[i - 1])
        if ref <= 0:
            continue
        if cur_low > prev_high and (cur_low - prev_high) / ref >= 0.005:
            t = int(df.index[i].timestamp())
            detail = f"向上缺口，缺口{round((cur_low-prev_high)/ref*100,1)}%" + _vol_note(df, i)
            return POSSIBLE, detail, [{"time": t, "price": round(prev_high, 4)}, {"time": t, "price": round(cur_low, 4)}]
        if cur_high < prev_low and (prev_low - cur_high) / ref >= 0.005:
            t = int(df.index[i].timestamp())
            detail = f"向下缺口，缺口{round((prev_low-cur_high)/ref*100,1)}%" + _vol_note(df, i)
            return POSSIBLE, detail, [{"time": t, "price": round(prev_low, 4)}, {"time": t, "price": round(cur_high, 4)}]
    return _empty("最近未見明顯缺口")


def _island(df: pd.DataFrame, lookback: int = 25) -> Tuple[str, str, List[Dict]]:
    """Two opposing gaps bracketing a small cluster of bars (the
    "island") -- net reverses the move that led into it."""
    n = len(df)
    start = max(1, n - lookback)
    gap_min_pct = 0.005
    events = []  # (idx, direction) direction: 'up' or 'down'
    for i in range(start, n):
        prev_high, prev_low = float(df["High"].iloc[i - 1]), float(df["Low"].iloc[i - 1])
        cur_high, cur_low = float(df["High"].iloc[i]), float(df["Low"].iloc[i])
        ref = float(df["Close"].iloc[i - 1])
        if ref <= 0:
            continue
        if cur_low > prev_high and (cur_low - prev_high) / ref >= gap_min_pct:
            events.append((i, "up"))
        elif cur_high < prev_low and (prev_low - cur_high) / ref >= gap_min_pct:
            events.append((i, "down"))
    if len(events) < 2:
        return _empty("未見兩個反向缺口")
    for j in range(len(events) - 1):
        idx1, dir1 = events[j]
        idx2, dir2 = events[j + 1]
        island_len = idx2 - idx1
        if dir1 != dir2 and 1 <= island_len <= 6:
            t1, t2 = int(df.index[idx1].timestamp()), int(df.index[idx2].timestamp())
            detail = f"{dir1}缺口後{island_len}日內再現{dir2}缺口，中間形成孤島" + _vol_note(df, idx2)
            return POSSIBLE, detail, [
                {"time": t1, "price": round(float(df['Close'].iloc[idx1]), 4)},
                {"time": t2, "price": round(float(df['Close'].iloc[idx2]), 4)},
            ]
    return _empty("兩個缺口之間唔構成孤島")


def detect_patterns(df: pd.DataFrame) -> Tuple[Dict[str, str], Dict[str, List[Dict]]]:
    """
    Main entry point. `df` is the SAME OHLC dataframe
    TechnicalAnalysisService.get_analysis() already fetched (DatetimeIndex,
    columns High/Low/Close) -- no extra network call.

    Returns (verdicts, points):
      verdicts -- {"p_double_top": "可能"|"不可能", ...} for all 17 keys,
                  identical key names/values chart-analysis.html's upload
                  flow already uses, so the existing frontend loop can
                  render either flow's result unchanged.
      points   -- {"p_double_top": [{"time":..,"price":..}, ...], ...} only
                  for patterns that came back "可能" -- real chart
                  coordinates for the on-chart drawing overlay. Not shown
                  in today's text-only UI; harmless extra data otherwise.
    """
    if df is None or df.empty or len(df) < 15:
        keys = list(PATTERN_CONFIDENCE.keys())
        return {k: NOT_POSSIBLE for k in keys}, {}

    all_pivots = _pivots(df)
    last_idx = len(df) - 1
    highs = _recent(all_pivots, "high", LOOKBACK_SWING, last_idx)
    lows = _recent(all_pivots, "low", LOOKBACK_SWING, last_idx)
    closes = df["Close"]

    verdicts: Dict[str, str] = {}
    points: Dict[str, List[Dict]] = {}

    def _set(key: str, result: Tuple[str, str, List[Dict]]):
        verdict, _detail, pts = result
        verdicts[key] = verdict
        if verdict == POSSIBLE and pts:
            points[key] = pts

    _set("p_double_top", _double_top(df, highs, lows, last_idx))
    _set("p_double_bottom", _double_bottom(df, highs, lows, last_idx))
    _set("p_head_shoulder_top", _head_shoulder_top(df, highs, lows, last_idx))
    _set("p_head_shoulder_bottom", _head_shoulder_bottom(df, highs, lows, last_idx))
    _set("p_triangle", _triangle(highs, lows))
    _set("p_channel", _channel(highs, lows))
    _set("p_rectangle", _rectangle(highs, lows))
    _set("p_broadening", _broadening(highs, lows))
    _set("p_breakback", _breakback(df, all_pivots, closes, last_idx))
    _set("p_0618", _fib_0618(highs, lows, closes))
    _set("p_cup_handle", _cup_handle(df, last_idx))
    _set("p_diamond", _diamond(highs, lows, last_idx))
    _set("p_abc", _abc(highs, lows, last_idx))
    _set("p_gap", _gap(df))
    _set("p_island", _island(df))

    flag_verdict, pennant_verdict, fp_detail, fp_pts = _flag_pennant(df, highs, lows, last_idx)
    verdicts["p_flag"] = flag_verdict
    verdicts["p_pennant"] = pennant_verdict
    if flag_verdict == POSSIBLE and fp_pts:
        points["p_flag"] = fp_pts
    if pennant_verdict == POSSIBLE and fp_pts:
        points["p_pennant"] = fp_pts

    return verdicts, points
