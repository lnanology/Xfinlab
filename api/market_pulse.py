"""
Live Market Pulse -- homepage-level "global sentiment" summary.

Part of the CRO/Neuro-UX homepage proposal (see
HOMEPAGE_CRO_REDESIGN_PROPOSAL.md, Phase E: 🟡 medium risk, but explicitly
flagged there as "無新增cost（用現有Alpaca/yfinance）" and not gated behind
any of the 🔴 high-risk decisions (no login-bypass AI cost, no fabricated
authority claims, no fabricated testimonials, no colour rebrand).

Design:
- Aggregates a small, fixed basket of broad-market + sector proxies (SPY/
  QQQ/DIA/IWM for broad US equities, XLK/XLF/XLE for sector rotation, plus
  BTC-USD for crypto) using the EXISTING, already-audited
  services/technical_analysis_service.py Confluence Engine -- same real
  price-action math (trend/RSI/MACD/support-resistance/Fibonacci) already
  used everywhere else on the site, zero AI-provider cost.
- Averages each basket member's confluence score into one overall
  sentiment reading, plus a per-ticker breakdown SORTED by confluence
  score (strongest first) so it reads as a sector-rotation leaderboard
  rather than a static grid -- "which sector is strongest right now" is
  more useful and more "alive" feeling than an unordered list.
- Cached in-memory for 5 minutes: this runs on every homepage load
  (including the client-side auto-refresh in index.html), so without a
  cache it would refetch 8 tickers' worth of history from Alpaca/yfinance
  on every single visitor/refresh cycle. A stale-by-5-minutes market
  sentiment reading is a completely reasonable tradeoff for a homepage
  widget (this is explicitly NOT the same code path as
  api/chart_analysis.py's ticker-specific analysis, which stays uncached
  beyond its own 10-minute AI-response cache).
"""

import os
import sqlite3
import time
from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter

from services.technical_analysis_service import get_technical_analysis

router = APIRouter()

_PULSE_BASKET = ["SPY", "QQQ", "DIA", "IWM", "XLK", "XLF", "XLE", "BTC-USD"]
_PULSE_LABELS = {
    "SPY": "美股大盤", "QQQ": "科技股", "DIA": "道瓊工業", "IWM": "小型股",
    "XLK": "科技板塊", "XLF": "金融板塊", "XLE": "能源板塊", "BTC-USD": "加密貨幣",
}

_CACHE_TTL_SECONDS = 300
_cache: Optional[Dict] = None
_cache_time: float = 0.0


def _compute_pulse() -> Dict:
    breakdown: List[Dict] = []
    scores: List[float] = []

    for ticker in _PULSE_BASKET:
        try:
            tech = get_technical_analysis(ticker, period="3mo")
        except Exception as e:
            tech = {"error": str(e)}

        if not tech or "error" in tech:
            breakdown.append({
                "ticker": ticker,
                "label": _PULSE_LABELS.get(ticker, ticker),
                "available": False,
            })
            continue

        confluence = tech.get("confluence", {})
        score = confluence.get("score", 0.0)
        scores.append(score)
        breakdown.append({
            "ticker": ticker,
            "label": _PULSE_LABELS.get(ticker, ticker),
            "available": True,
            "price": tech.get("last_close"),
            "trend": tech.get("trend"),
            "rsi": tech.get("rsi"),
            "confluence_direction": confluence.get("direction"),
            "confluence_score": score,
            # Added alongside the frontend's Volume/Probability display on
            # the Today's AI Outlook cards -- both come straight from the
            # same real Confluence Engine call above, nothing new fetched.
            "confluence_confidence_pct": confluence.get("confidence_pct"),
            "volume_desc": tech.get("volume_desc"),
        })

    if scores:
        avg_score = round(sum(scores) / len(scores), 1)
    else:
        avg_score = 0.0

    if not scores:
        overall = "數據不足"
    elif avg_score >= 20:
        overall = "偏多"
    elif avg_score <= -20:
        overall = "偏空"
    else:
        overall = "訊號分歧，中性"

    # Simple dispersion-based "volatility" read: how spread out the basket's
    # individual scores are from the average -- wide spread = markets
    # disagreeing with each other = choppier/more uncertain conditions.
    if len(scores) >= 2:
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        dispersion = round(variance ** 0.5, 1)
    else:
        dispersion = None

    if dispersion is None:
        volatility_desc = "數據不足"
    elif dispersion >= 50:
        volatility_desc = "市場分歧大"
    elif dispersion >= 25:
        volatility_desc = "中等波動"
    else:
        volatility_desc = "市場方向一致"

    # Sort available members by confluence score descending -- turns the
    # basket into a sector-rotation leaderboard ("what's strongest right
    # now") instead of a fixed-order grid. Unavailable members (data fetch
    # failed) sort last so the ranking only reflects real data.
    available = [b for b in breakdown if b.get("available")]
    unavailable = [b for b in breakdown if not b.get("available")]
    available.sort(key=lambda b: b["confluence_score"], reverse=True)
    sorted_breakdown = available + unavailable
    top_sector = available[0] if available else None
    # Weakest/most-bearish member of the basket -- symmetric to top_sector,
    # same real per-ticker confluence data, just picking the other end of
    # the sorted list. Used by index.html's "Today's AI Outlook" summary
    # as an honest "Top Risk" figure (not a separate risk model -- just
    # which basket member currently has the worst real signal).
    bottom_sector = available[-1] if len(available) > 1 else None

    return {
        "overall_sentiment": overall,
        "overall_score": avg_score,
        # Confidence framing of the same overall_score: how strongly the
        # basket agrees in one direction, as a 0-100 magnitude.
        "confidence_pct": round(min(100.0, abs(avg_score)), 1),
        "volatility_desc": volatility_desc,
        "top_sector": {
            "label": top_sector["label"],
            "ticker": top_sector["ticker"],
            "confluence_direction": top_sector["confluence_direction"],
            "confluence_confidence_pct": top_sector.get("confluence_confidence_pct"),
            "volume_desc": top_sector.get("volume_desc"),
        } if top_sector else None,
        "bottom_sector": {
            "label": bottom_sector["label"],
            "ticker": bottom_sector["ticker"],
            "confluence_direction": bottom_sector["confluence_direction"],
            "confluence_confidence_pct": bottom_sector.get("confluence_confidence_pct"),
            "volume_desc": bottom_sector.get("volume_desc"),
        } if bottom_sector else None,
        "basket": sorted_breakdown,
        "data_source": "即市技術分析（真實價格數據，非AI猜測）",
        "disclaimer": "呢個係整體市場技術面參考，唔係投資建議。",
    }


@router.get("/market-pulse")
def market_pulse():
    global _cache, _cache_time

    now = time.time()
    if _cache is not None and (now - _cache_time) < _CACHE_TTL_SECONDS:
        return {**_cache, "cached": True}

    result = _compute_pulse()
    _cache = result
    _cache_time = now
    return {**result, "cached": False}


# ---------------------------------------------------------------------------
# Top Opportunity (per-asset-class) -- homepage "Top Opportunity" section
# (product decision 2026-07-13): instead of one global top pick across a
# mixed basket, show a top pick PER asset class (stock/futures/crypto) so
# visitors can see "what's strongest right now" in the asset class they
# actually care about. Reuses the exact same Confluence Engine + caching
# pattern as _compute_pulse() above -- zero new external dependencies,
# same real price-action math, same "no AI-provider cost" property.
#
# Futures use yfinance's continuous-contract front-month symbols (ES=F/
# CL=F/GC=F); crypto adds ETH-USD alongside the existing BTC-USD. Alpaca
# doesn't cover futures/crypto so these fall through to yfinance inside
# get_technical_analysis(), same fallback path already exercised by
# BTC-USD in the main pulse basket above.
# ---------------------------------------------------------------------------

_ASSET_CLASS_BASKETS = {
    "stock": ["SPY", "QQQ", "DIA", "IWM", "XLK", "XLF", "XLE"],
    "futures": ["ES=F", "CL=F", "GC=F"],
    "crypto": ["BTC-USD", "ETH-USD"],
}
_ASSET_CLASS_LABELS = {"stock": "股票", "futures": "期貨", "crypto": "加密貨幣"}
_TICKER_LABELS = {
    "SPY": "標普500", "QQQ": "納指100", "DIA": "道瓊工業", "IWM": "羅素2000小型股",
    "XLK": "科技板塊", "XLF": "金融板塊", "XLE": "能源板塊",
    "ES=F": "標普500期貨", "CL=F": "原油期貨", "GC=F": "黃金期貨",
    "BTC-USD": "比特幣", "ETH-USD": "以太幣",
}

_TOP_OPP_CACHE_TTL_SECONDS = 300
_top_opp_cache: Optional[Dict] = None
_top_opp_cache_time: float = 0.0


def _compute_top_opportunities() -> Dict:
    items: Dict[str, Dict] = {}

    for asset_class, basket in _ASSET_CLASS_BASKETS.items():
        best: Optional[Dict] = None
        for ticker in basket:
            try:
                tech = get_technical_analysis(ticker, period="3mo")
            except Exception:
                tech = None
            if not tech or "error" in tech:
                continue

            confluence = tech.get("confluence", {})
            score = confluence.get("score", 0.0)
            candidate = {
                "ticker": ticker,
                "label": _TICKER_LABELS.get(ticker, ticker),
                "price": tech.get("last_close"),
                "confluence_direction": confluence.get("direction"),
                "confluence_confidence_pct": confluence.get("confidence_pct"),
                "volume_desc": tech.get("volume_desc"),
                "_score": score,
            }
            if best is None or score > best["_score"]:
                best = candidate

        if best:
            items[asset_class] = {
                "asset_class": asset_class,
                "asset_class_label": _ASSET_CLASS_LABELS[asset_class],
                "available": True,
                "ticker": best["ticker"],
                "label": best["label"],
                "price": best["price"],
                "confluence_direction": best["confluence_direction"],
                "confluence_confidence_pct": best.get("confluence_confidence_pct"),
                "volume_desc": best.get("volume_desc"),
            }
        else:
            items[asset_class] = {
                "asset_class": asset_class,
                "asset_class_label": _ASSET_CLASS_LABELS[asset_class],
                "available": False,
            }

    return {
        "items": items,
        "data_source": "即市技術分析（真實價格數據，非AI猜測）",
        "disclaimer": "呢個係整體市場技術面參考，唔係投資建議。",
    }


@router.get("/top-opportunities")
def top_opportunities():
    global _top_opp_cache, _top_opp_cache_time

    now = time.time()
    if _top_opp_cache is not None and (now - _top_opp_cache_time) < _TOP_OPP_CACHE_TTL_SECONDS:
        return {**_top_opp_cache, "cached": True}

    result = _compute_top_opportunities()
    _top_opp_cache = result
    _top_opp_cache_time = now
    return {**result, "cached": False}


# ---------------------------------------------------------------------------
# Free Signals -- new site-wide "Free Signals" page/feature. Reuses the
# exact same fixed candidate baskets + Confluence Engine as
# _compute_top_opportunities() above (no new external data source, no AI
# cost), but instead of picking one winner PER asset class, it scores every
# basket member across ALL classes and ranks them by |confluence score| --
# i.e. "which real, live signals are currently the most confident calls
# right now", regardless of which asset class they happen to be in.
#
# The result is regenerated once per CALENDAR DAY (not just a short TTL
# cache like the other two endpoints above) so that "today's free signals"
# reads as a stable daily list for marketing/consistency purposes -- a
# visitor who checks back later the same day sees the same list, and it's
# clearly a "daily" feature rather than something that reshuffles every 5
# minutes.
#
# Tier gating: everyone (including signed-out visitors) sees the top 3
# signals for free. Logged-in paid-tier users (anything other than "free")
# get the full top 6 -- the extra 3 are reported to free/signed-out callers
# as `locked_count` so the frontend can render blurred/teaser rows with an
# upgrade CTA, without ever sending the actual locked signal data to a
# free-tier client.
# ---------------------------------------------------------------------------

_FREE_SIGNALS_VISIBLE_FREE = 3
_FREE_SIGNALS_VISIBLE_PAID = 6

_free_signals_cache: Optional[Dict] = None
_free_signals_cache_date: Optional[str] = None


def _compute_all_signals() -> List[Dict]:
    candidates: List[Dict] = []
    for asset_class, basket in _ASSET_CLASS_BASKETS.items():
        for ticker in basket:
            try:
                tech = get_technical_analysis(ticker, period="3mo")
            except Exception:
                tech = None
            if not tech or "error" in tech:
                continue

            confluence = tech.get("confluence", {})
            score = confluence.get("score", 0.0)
            candidates.append({
                "asset_class": asset_class,
                "asset_class_label": _ASSET_CLASS_LABELS[asset_class],
                "ticker": ticker,
                "label": _TICKER_LABELS.get(ticker, ticker),
                "price": tech.get("last_close"),
                "confluence_direction": confluence.get("direction"),
                "confluence_confidence_pct": confluence.get("confidence_pct"),
                "volume_desc": tech.get("volume_desc"),
                "_score": score,
            })

    # Strongest conviction first, whichever direction it points -- a
    # confident bearish call is just as much a "signal" as a confident
    # bullish one.
    candidates.sort(key=lambda c: abs(c["_score"]), reverse=True)
    for c in candidates:
        c.pop("_score", None)
    return candidates


def _compute_free_signals() -> Dict:
    signals = _compute_all_signals()
    for i, s in enumerate(signals):
        s["rank"] = i + 1
    return {
        "date": date.today().isoformat(),
        "signals": signals,
        "data_source": "即市技術分析（真實價格數據，非AI猜測）",
        "disclaimer": "呢個係整體市場技術面參考，唔係投資建議。",
    }


def _lookup_plan(token: Optional[str]) -> str:
    """Best-effort plan lookup from a JWT -- mirrors api/quota.py's
    pattern. Returns "free" for missing/invalid tokens or any lookup
    failure (fail open to the free tier, never fail the request)."""
    if not token:
        return "free"
    try:
        from backend.auth.jwt_handler import verify_token
        payload = verify_token(token)
        if not payload:
            return "free"
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT plan FROM users WHERE id=?", (payload["id"],)).fetchone()
        conn.close()
        return (row["plan"] if row and row["plan"] else "free")
    except Exception:
        return "free"


@router.get("/free-signals")
def free_signals(token: Optional[str] = None):
    global _free_signals_cache, _free_signals_cache_date

    today = date.today().isoformat()
    if _free_signals_cache is None or _free_signals_cache_date != today:
        _free_signals_cache = _compute_free_signals()
        _free_signals_cache_date = today

    result = _free_signals_cache
    plan = _lookup_plan(token)
    is_paid = plan not in ("free", None, "")

    all_signals = result["signals"]
    visible_n = _FREE_SIGNALS_VISIBLE_PAID if is_paid else _FREE_SIGNALS_VISIBLE_FREE
    visible = all_signals[:visible_n]
    locked_count = max(0, len(all_signals) - visible_n)

    return {
        "date": result["date"],
        "signals": visible,
        "locked_count": locked_count,
        "plan": plan,
        "data_source": result["data_source"],
        "disclaimer": result["disclaimer"],
    }
