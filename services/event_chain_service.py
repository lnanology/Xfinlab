"""
Event Chain Service -- Phase 5 of the AI Intelligence Engine (2026-07-31).

Builds the `event_chain` field Phases 1-4 deliberately left as None. The
original 5-phase plan flagged this as the hardest/most speculative phase
and specifically warned it needs a NON-causal treatment: the user's
proposal's "AI Event Graph" concept (Fed -> USD -> Gold/Oil/BTC) reads as
an asserted causal chain. This codebase has no causal-inference engine,
and claiming "X causes Y" purely from historical co-movement data would
be a textbook correlation/causation error -- exactly the kind of
precision-looking-but-unfounded number this codebase's anti-fabrication
convention (chart_pattern_service.py's PATTERN_CONFIDENCE, market_
structure_engine.py's `weights_calibrated: False`, Phase 1-2's
quant_pending discipline) exists to prevent.

What this actually computes instead: for each of a news event's
affected_assets that has a documented "commonly co-discussed" downstream
asset (see _CHAIN_MAP below -- small, disclosed, manually curated, same
"v1 heuristic, incomplete" honesty as ai_news_object_service.py's
_KNOWN_ENTITIES), it reuses historical_analog_service.py's exact regime-
matching methodology (current trend regime via SMA50, same convention)
but applies it CROSS-ASSET: on every historical date the PRIMARY asset
was in the same trend regime as today, what did the CANDIDATE asset's
forward return actually look like? This is an honest historical
co-movement statistic reusing services/backtest_service.py's and
historical_analog_service.py's established "regime -> forward return"
backtest pattern -- every returned edge is explicitly labeled
`causal: False` with a `methodology` string stating plainly this is not
a causal claim, same disclosure posture as every other engine here.

_CHAIN_MAP only covers tickers already present in
ai_news_object_service._KNOWN_ENTITIES -- extend both together if a new
entity is ever added there. Any affected_asset without a mapped
candidate simply produces no edge for that ticker (never a fabricated
one); if NO affected_asset has a mapped candidate, event_chain is left
completely untouched (still None from Phase 1), never set to an empty
list that could be misread as "checked, nothing found" vs. "not mapped
yet".
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from services.market_data_gateway import get_ohlc

logger = logging.getLogger(__name__)

WARMUP_BARS = 50
FORWARD_DAYS_DEFAULT = 5
# Bounds latency/cost -- each edge needs 2 real OHLC fetches (primary +
# candidate) plus a regime computation on each, same cost-awareness as
# news_impact_engine.py's _DEFAULT_MAX_ASSETS cap.
MAX_CHAIN_EDGES = 2

# v1 heuristic, NOT a causal model -- see module docstring. Downstream
# tickers are commonly-cited macro/sector-linked assets, not asserted
# effects. (ticker, Cantonese label) tuples, keyed by the primary ticker
# as it appears in ai_news_object_service._KNOWN_ENTITIES.
_CHAIN_MAP: Dict[str, List[Tuple[str, str]]] = {
    "FED": [("GLD", "黃金ETF"), ("UUP", "美元指數ETF"), ("TLT", "美國長債ETF")],
    "ECB": [("FXE", "歐元ETF")],
    "BOJ": [("FXY", "日圓ETF")],
    "BOE": [("FXB", "英鎊ETF")],
    "AAPL": [("QQQ", "納指100 ETF")],
    "MSFT": [("QQQ", "納指100 ETF")],
    "GOOGL": [("QQQ", "納指100 ETF")],
    "META": [("QQQ", "納指100 ETF")],
    "AMZN": [("QQQ", "納指100 ETF")],
    "NVDA": [("SMH", "半導體ETF")],
    "AMD": [("SMH", "半導體ETF")],
    "INTC": [("SMH", "半導體ETF")],
    "AVGO": [("SMH", "半導體ETF")],
    "TSM": [("SMH", "半導體ETF")],
    "XOM": [("XLE", "能源業ETF")],
    "CVX": [("XLE", "能源業ETF")],
    "JPM": [("XLF", "金融業ETF")],
    "GS": [("XLF", "金融業ETF")],
}


def _compute_trend_dir(closes: np.ndarray) -> np.ndarray:
    """Same SMA50-vs-close trend convention as
    historical_analog_service.find_analogs() -- +1 above its own 50-bar
    (or shorter, if history is thin) moving average, -1 below."""
    n = len(closes)
    window = min(50, n)
    sma = pd.Series(closes).rolling(window).mean().values
    return np.where(closes > sma, 1, -1)


def _cross_asset_edge(primary: str, candidate_ticker: str, candidate_label: str,
                       forward_days: int = FORWARD_DAYS_DEFAULT) -> Dict:
    """Returns one event_chain edge dict. Any data failure is captured
    under the edge's own `error`/`note` key -- never raises, never
    fabricates a stat from insufficient data."""
    edge = {
        "from": primary,
        "to": candidate_ticker,
        "to_label": candidate_label,
        "causal": False,
    }
    try:
        primary_df = get_ohlc(primary, period="2y", interval="1d")
        candidate_df = get_ohlc(candidate_ticker, period="2y", interval="1d")
    except Exception as e:
        edge["error"] = f"OHLC 數據攞唔到（{primary}/{candidate_ticker}）：{e}"
        return edge

    if primary_df is None or primary_df.empty or candidate_df is None or candidate_df.empty:
        edge["error"] = f"OHLC 數據為空（{primary}/{candidate_ticker}）"
        return edge

    merged = primary_df[["Close"]].join(
        candidate_df[["Close"]], lsuffix="_primary", rsuffix="_candidate", how="inner",
    )
    if len(merged) < WARMUP_BARS + forward_days + 10:
        edge["error"] = f"{primary} 同 {candidate_ticker} 共同歷史數據不足"
        return edge

    primary_close = merged["Close_primary"].values
    candidate_close = merged["Close_candidate"].values
    trend = _compute_trend_dir(primary_close)
    current_trend = trend[-1]
    n = len(merged)

    fwd_returns = []
    for i in range(WARMUP_BARS, n - forward_days):
        if trend[i] != current_trend:
            continue
        entry = float(candidate_close[i])
        exit_ = float(candidate_close[i + forward_days])
        if entry > 0:
            fwd_returns.append((exit_ - entry) / entry * 100)

    edge["primary_current_trend"] = "偏多" if current_trend == 1 else "偏空"
    if not fwd_returns:
        edge["note"] = f"{primary} 同 {candidate_ticker} 未有足夠歷史類比樣本"
        return edge

    arr = np.array(fwd_returns)
    edge["match_count"] = len(arr)
    edge["forward_days"] = forward_days
    edge["candidate_win_rate_pct"] = round(float((arr > 0).sum() / len(arr) * 100), 1)
    edge["candidate_avg_forward_return_pct"] = round(float(arr.mean()), 2)
    edge["methodology"] = (
        f"喺 {primary} 過去處於同現時相同（{edge['primary_current_trend']}）趨勢嘅日子，"
        f"睇返 {candidate_ticker} 之後 {forward_days} 個交易日嘅實際歷史表現。"
        f"呢個係歷史共同走勢統計，並非話 {primary} 引致 {candidate_ticker} 變動嘅因果關係，"
        "亦非投資建議或者未來預測。"
    )
    return edge


def add_event_chain(news_object: Dict, max_edges: int = MAX_CHAIN_EDGES) -> Dict:
    """
    Mutates and returns `news_object`, filling `event_chain` with a list
    of non-causal cross-asset historical co-movement edges for whichever
    of its `affected_assets` have a documented candidate in _CHAIN_MAP.

    Leaves `event_chain` as None (untouched, same Phase-1 placeholder) if
    no affected_asset has a mapped candidate -- this function never
    invents a chain out of nothing, and never sets an empty list where
    "not mapped" and "checked, found nothing" would be indistinguishable.
    """
    tickers = news_object.get("affected_assets") or []
    candidates: List[Tuple[str, str, str]] = []
    for t in tickers:
        for cand_ticker, cand_label in _CHAIN_MAP.get(t, []):
            candidates.append((t, cand_ticker, cand_label))
    candidates = candidates[:max_edges]

    if not candidates:
        return news_object

    edges = []
    for primary, cand_ticker, cand_label in candidates:
        try:
            edges.append(_cross_asset_edge(primary, cand_ticker, cand_label))
        except Exception as e:
            logger.warning("event_chain_service: edge %s->%s failed: %s", primary, cand_ticker, e)
            edges.append({"from": primary, "to": cand_ticker, "to_label": cand_label,
                           "causal": False, "error": str(e)})

    news_object["event_chain"] = edges
    return news_object


if __name__ == "__main__":
    import json

    sample = {"id": "news_test", "affected_assets": ["FED"]}
    result = add_event_chain(dict(sample))
    print(json.dumps(result, indent=2, ensure_ascii=False))
