"""
Shipping / Supply-Chain Proxy Indicator -- Stage 3 roadmap item 3 (2026-07-20):
"航運/供應鏈壓力代理指標".

Honest scope: this is NOT the official Baltic Dry Index (BDI). The BDI
itself is a licensed, subscription-only benchmark published by the Baltic
Exchange -- XFINLAB has no paid feed for it, and inventing a number to look
like BDI would violate this codebase's core "never fabricate a number"
principle.

Instead, this builds a proxy from REAL, freely available market data: the
traded price of shipping-sector ETFs, routed through the same
Alpaca-first/yfinance-fallback OHLC infra every other real-data feature in
this codebase uses (services/technical_analysis_service.fetch_ohlc_history).
Every output field is explicitly labeled "proxy" and states its actual
composition, so it can never be confused with the real BDI.

Tickers used (both real, actively-traded ETFs -- verified via web search,
July 2026):
  - BDRY: Breakwave Dry Bulk Shipping ETF -- holds dry-bulk freight futures
    (Capesize/Panamax/Supramax), the closest freely-tradeable market proxy
    to actual Baltic-index freight-rate conditions.
  - BOAT: SonicShares Global Shipping ETF -- holds shipping-sector equities
    (container/tanker/dry-bulk operators). A noisier, indirect signal --
    equities react to fuel costs, order books and sentiment, not just spot
    freight rates -- disclosed as such rather than overclaiming precision.

Optional future extension (NOT implemented here): a real official Baltic Dry
Index feed via a licensed provider (e.g. OilPriceAPI), gated behind an
OILPRICEAPI_KEY env var the user would need to configure and pay for
themselves -- tracked as follow-up rather than built speculatively against
an unverified/unpaid ToS, the same reasoning that led this codebase to
previously reject StockTwits and prefer SEC EDGAR over paid FMP (see
services/license_registry.py).
"""

import logging
import time
from typing import Dict, Optional

from services.technical_analysis_service import fetch_ohlc_history

logger = logging.getLogger(__name__)

MIN_OBSERVATIONS = 20

# This proxy is market-wide (BDRY/BOAT), not specific to whatever symbol the
# caller is analyzing -- api/ai_analysis.py calls it once per analysis
# request regardless of which stock/crypto/future the user searched. Without
# a cache, every single analysis request would re-fetch the same two ETFs'
# OHLC history, multiplying real network calls for no new information (the
# underlying real data itself doesn't move meaningfully within a few
# minutes). A short in-process TTL cache avoids that redundant load while
# still refreshing often enough to stay honest/current.
_CACHE_TTL_SECONDS = 15 * 60
_cache: Optional[Dict] = None
_cache_ts: float = 0.0

SHIPPING_PROXY_TICKERS = {
    "BDRY": {
        "name": "Breakwave Dry Bulk Shipping ETF",
        "basis": "dry-bulk freight futures (Capesize/Panamax/Supramax)",
    },
    "BOAT": {
        "name": "SonicShares Global Shipping ETF",
        "basis": "shipping-sector equities (container/tanker/dry-bulk operators)",
    },
}


def _trend_label(pct_change: float) -> str:
    if pct_change >= 5:
        return "RISING"
    if pct_change <= -5:
        return "FALLING"
    return "FLAT"


def _one_ticker_proxy(ticker: str, period: str = "3mo") -> Dict:
    meta = SHIPPING_PROXY_TICKERS[ticker]
    try:
        df = fetch_ohlc_history(ticker, period=period, interval="1d")
    except Exception as e:
        return {"available": False, "ticker": ticker, "message": f"攞唔到 {ticker} 嘅歷史數據：{e}"}

    if df is None or "Close" not in df.columns or len(df) < MIN_OBSERVATIONS:
        return {"available": False, "ticker": ticker, "message": f"{ticker} 嘅真實歷史數據唔夠"}

    closes = df["Close"].astype(float).values
    latest_close = float(closes[-1])
    lookback = min(21, len(closes) - 1)  # ~1 trading month
    pct_change_1m = float((closes[-1] / closes[-1 - lookback] - 1) * 100) if lookback > 0 else 0.0

    return {
        "available": True,
        "ticker": ticker,
        "name": meta["name"],
        "basis": meta["basis"],
        "latest_close": round(latest_close, 2),
        "pct_change_1m": round(pct_change_1m, 2),
        "trend": _trend_label(pct_change_1m),
        "n_observations": int(len(closes)),
    }


def get_shipping_proxy(period: str = "3mo", use_cache: bool = True) -> Dict:
    """
    Returns per-ticker real market data plus an honestly-labeled combined
    proxy read:
        {"available": True,
         "tickers": {"BDRY": {...}, "BOAT": {...}},
         "combined_trend": "RISING" | "FALLING" | "FLAT" | "MIXED",
         "n_tickers_available": int,
         "method": "...",
         "disclaimer": "..."}

    Only returns available=False when BOTH tickers fail to fetch -- a single
    ticker's real data is still a real (if narrower) signal, not fabricated,
    so it's surfaced with its own per-ticker availability flag rather than
    being hidden entirely.

    Market-wide (not symbol-specific), so callers hit a short TTL cache by
    default -- see module docstring for why.
    """
    global _cache, _cache_ts
    if use_cache and _cache is not None and (time.time() - _cache_ts) < _CACHE_TTL_SECONDS:
        return _cache

    results = {t: _one_ticker_proxy(t, period=period) for t in SHIPPING_PROXY_TICKERS}
    available_results = [r for r in results.values() if r["available"]]

    if not available_results:
        # Don't cache a failure -- a transient network hiccup shouldn't be
        # frozen as "unavailable" for the full TTL window; let the next
        # request retry immediately.
        return {
            "available": False,
            "tickers": results,
            "message": "航運ETF代理指標暫時攞唔到真實數據",
        }

    trends = {r["trend"] for r in available_results}
    combined_trend = next(iter(trends)) if len(trends) == 1 else "MIXED"

    result = {
        "available": True,
        "tickers": results,
        "combined_trend": combined_trend,
        "n_tickers_available": len(available_results),
        "method": "real traded price of shipping-sector ETFs (BDRY/BOAT), NOT the official Baltic Dry Index",
        "disclaimer": (
            "呢個係航運類ETF嘅真實市場價格代理指標，並非官方Baltic Dry Index（未有授權數據源）。"
            "BDRY追蹤散裝乾貨運費期貨，BOAT係航運股票組合，兩者反映供應鏈/航運狀況嘅方向，"
            "但唔完全等同即期運費本身，僅供參考，不構成投資建議。"
        ),
    }
    _cache = result
    _cache_ts = time.time()
    return result


if __name__ == "__main__":
    import json

    print(json.dumps(get_shipping_proxy(), indent=2, ensure_ascii=False))
