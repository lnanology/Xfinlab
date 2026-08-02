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

from services.technical_analysis_service import get_technical_analysis, fetch_ohlc_history
from services.trending_stocks_service import get_trending_for_country

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
        row = conn.execute("SELECT plan, plan_expires_at FROM users WHERE id=?", (payload["id"],)).fetchone()
        conn.close()
        if not row or not row["plan"]:
            return "free"
        from services.quota_middleware import resolve_real_plan
        return resolve_real_plan(row)
    except Exception:
        return "free"


def _feature_flag_enabled(key: str, default: bool = True) -> bool:
    """Best-effort feature-flag lookup, same feature_flags table api/
    admin.py's Feature Flags panel writes to. Fails open to `default` if
    the table/row doesn't exist yet or the DB is unreachable -- a flag
    check must never be the reason a daily job crashes."""
    try:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT enabled FROM feature_flags WHERE key=?", (key,)).fetchone()
        conn.close()
        if row is None:
            return default
        return bool(row[0])
    except Exception:
        return default


def _notify_free_signals_ready(today: str, cache: Dict):
    # Best-effort daily push. Guarded by a persisted push_send_log row so
    # this only ever fires once per calendar day no matter how many
    # times the cache gets (re)computed that day -- whether triggered by
    # the scheduled cron job below or by the lazy per-request fallback.
    # Any failure here must never break the caller, hence the broad except.
    try:
        from services.push_service import already_sent_today, mark_sent_today, send_push_to_all

        key = "free_signals_daily"
        if already_sent_today(key, today):
            return

        top = (cache.get("signals") or [])[:1]
        top_ticker = top[0]["ticker"] if top else None
        body = f"今日焦點：{top_ticker}" if top_ticker else "睇下今日邊啲資產訊號最強。"
        send_push_to_all({
            "title": "🎯 XFINLAB 今日免費訊號已出爐",
            "body": body,
            "url": "/free-signals.html",
        })
        mark_sent_today(key, today)
    except Exception:
        pass

    # Separate idempotency key so a Telegram-side failure/misconfig never
    # blocks (or gets blocked by) the web-push send above. Re-imports the
    # shared push_send_log helpers independently of the block above so
    # this doesn't rely on that try succeeding first.
    try:
        from services.push_service import already_sent_today, mark_sent_today
        from services.telegram_push_service import push_daily_signals_to_telegram

        tg_key = "telegram_daily_signals"
        if already_sent_today(tg_key, today):
            return
        push_daily_signals_to_telegram(cache)
        mark_sent_today(tg_key, today)
    except Exception:
        pass

    # 2026-07-27 "Level 1 content leverage" growth batch: generate (and
    # persist) ready-to-copy-paste post text for X/Threads/LinkedIn/
    # Facebook/email/push from the SAME real signals data used above --
    # this does NOT post anywhere itself (no OAuth app on file for those
    # platforms), it just saves the text for the admin panel to display.
    # Own idempotency key so a failure/skip here never blocks (or is
    # blocked by) the two notification sends above.
    try:
        from services.push_service import already_sent_today, mark_sent_today
        from services.content_repurpose_service import (
            generate_content_variants,
            generate_content_variants_multilang,
            save_variants,
        )

        cv_key = "content_variants_daily"
        if already_sent_today(cv_key, today):
            return
        variants = generate_content_variants(cache)
        # Growth OS Phase 2 (2026-08-02): also fan out EN/ES social
        # variants using the same signals, gated by the
        # content_engine_multilang feature flag (default ON) so it can be
        # switched off from the admin panel without a redeploy if it's
        # ever not wanted. Best-effort within the already-best-effort
        # outer try/except -- a failure here must not lose the base "zh"
        # variants that already succeeded above.
        try:
            if _feature_flag_enabled("content_engine_multilang"):
                variants["multilang"] = generate_content_variants_multilang(cache)
        except Exception:
            pass
        save_variants(today, variants)
        mark_sent_today(cv_key, today)
    except Exception:
        pass


def _refresh_free_signals_cache():
    """Recompute the free-signals cache for "today" and fire the daily
    push notification. Shared by both trigger paths below so the logic
    can't drift between them."""
    global _free_signals_cache, _free_signals_cache_date
    today = date.today().isoformat()
    _free_signals_cache = _compute_free_signals()
    _free_signals_cache_date = today
    _notify_free_signals_ready(today, _free_signals_cache)


def refresh_free_signals_and_notify():
    """Entry point for the real scheduled job (APScheduler BackgroundScheduler,
    wired up in backend/main.py) that recomputes the cache and sends the
    push at a fixed time every day -- e.g. 08:00 Asia/Hong_Kong -- instead
    of only whenever the first visitor of the day happens to hit
    /api/free-signals. Safe to call redundantly: _notify_free_signals_ready's
    push_send_log guard makes any given day's push idempotent regardless
    of whether the scheduler or the lazy per-request fallback got there
    first."""
    _refresh_free_signals_cache()


@router.get("/free-signals")
def free_signals(token: Optional[str] = None):
    today = date.today().isoformat()
    if _free_signals_cache is None or _free_signals_cache_date != today:
        # Fallback path -- normally the scheduled job above already
        # refreshed the cache for today before anyone visits. This just
        # covers the scheduler being late, disabled, or the process
        # having just restarted.
        _refresh_free_signals_cache()

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


# ---------------------------------------------------------------------------
# 9-Category Opportunity Board -- new homepage section (2026-07-21), sitting
# alongside (not replacing) the existing 3-card Top Opportunity section.
# 9 categories: fund flow / sentiment / trending / fastest growth / best
# opportunity / highest yield / long-term / mid-term / short-term.
#
# Every category is backed by real, already-audited data -- no fabricated
# numbers (matches this codebase's standing rule, see e.g. the
# stress-lab.html and feature_engine.py fixes earlier in the project log):
#   - fund_flow / sentiment reuse _compute_pulse()'s existing sector-rotation
#     basket (SPY/QQQ/DIA/IWM/XLK/XLF/XLE/BTC-USD) -- zero new fetches when
#     the pulse cache is warm.
#   - trending reuses services/trending_stocks_service.py (already cached
#     per-day).
#   - best_opportunity reuses _compute_all_signals()'s existing cross-asset
#     Confluence ranking -- zero new fetches.
#   - fastest_growth is a real trailing-1-month % price change scan.
#   - highest_yield is a real yfinance dividend-yield scan over a small
#     curated basket of well-known dividend names/ETFs.
#   - long/mid/short_term each re-run the existing Confluence Engine at a
#     different timeframe (weekly / daily / 1-hour) over the same combined
#     basket used by Top Opportunity + Free Signals, then pick the
#     strongest real signal at that timeframe.
# ---------------------------------------------------------------------------

_DIVIDEND_BASKET = ["SCHD", "VYM", "JEPI", "VZ", "T", "XOM", "JNJ", "KO", "PFE", "MO"]
_DIVIDEND_LABELS = {
    "SCHD": "Schwab美股高股息ETF", "VYM": "Vanguard高股息ETF", "JEPI": "JPMorgan股息收益ETF",
    "VZ": "Verizon", "T": "AT&T", "XOM": "埃克森美孚", "JNJ": "強生",
    "KO": "可口可樂", "PFE": "輝瑞", "MO": "奧馳亞",
}

_TIMEFRAME_SCAN = {
    "long_term": {"period": "2y", "interval": "1wk", "label": "週線"},
    "mid_term": {"period": "6mo", "interval": "1d", "label": "日線"},
    "short_term": {"period": "5d", "interval": "1h", "label": "1小時"},
}

_NINE_CAT_CACHE_TTL_SECONDS = 600
_nine_cat_cache: Optional[Dict] = None
_nine_cat_cache_time: float = 0.0


def _compute_fastest_growth() -> Optional[Dict]:
    best = None
    for ticker in _ASSET_CLASS_BASKETS["stock"] + _ASSET_CLASS_BASKETS["futures"] + _ASSET_CLASS_BASKETS["crypto"]:
        try:
            hist = fetch_ohlc_history(ticker, period="1mo")
            if hist is None or hist.empty or "Close" not in hist:
                continue
            first_close = float(hist["Close"].iloc[0])
            last_close = float(hist["Close"].iloc[-1])
            # 2026-07-25 fix: `x <= 0` is always False when x is NaN (a
            # stray NaN Close row occasionally survives yfinance/Alpaca
            # history without raising), so this guard alone didn't catch a
            # NaN first/last close -- pct_change then computed as NaN too.
            # Previously that silently 500'd the WHOLE /opportunity-
            # categories request (services/safe_json.py's SafeJSONResponse
            # now converts it to null instead, which is safe for the
            # response but showed up as a literal "null%" on this one
            # homepage card while every other card loaded fine). Filtering
            # NaN explicitly here keeps this candidate out of the running
            # entirely, same as any other bad-data ticker.
            if first_close != first_close or last_close != last_close or first_close <= 0:
                continue
            pct_change = round((last_close - first_close) / first_close * 100, 2)
        except Exception:
            continue
        if best is None or pct_change > best["pct_change_1mo"]:
            best = {
                "ticker": ticker,
                "label": _TICKER_LABELS.get(ticker, ticker),
                "pct_change_1mo": pct_change,
                "last_close": last_close,
            }
    return best


def _compute_highest_yield() -> Optional[Dict]:
    import yfinance as yf

    best = None
    for ticker in _DIVIDEND_BASKET:
        try:
            info = yf.Ticker(ticker).info
            yield_raw = info.get("dividendYield") or info.get("trailingAnnualDividendYield")
            if not yield_raw:
                continue
            # yfinance has changed whether this field is already a % (e.g.
            # 3.2) or a fraction (0.032) across versions -- normalize by
            # treating anything under 1 as a fraction.
            yield_pct = yield_raw * 100 if yield_raw < 1 else yield_raw
        except Exception:
            continue
        if best is None or yield_pct > best["dividend_yield_pct"]:
            best = {
                "ticker": ticker,
                "label": _DIVIDEND_LABELS.get(ticker, ticker),
                "dividend_yield_pct": round(yield_pct, 2),
            }
    return best


def _compute_best_at_timeframe(period: str, interval: str) -> Optional[Dict]:
    best = None
    basket = _ASSET_CLASS_BASKETS["stock"] + _ASSET_CLASS_BASKETS["futures"] + _ASSET_CLASS_BASKETS["crypto"]
    for ticker in basket:
        try:
            tech = get_technical_analysis(ticker, period=period, interval=interval)
        except Exception:
            tech = None
        if not tech or "error" in tech:
            continue
        confluence = tech.get("confluence", {})
        score = confluence.get("score", 0.0)
        if best is None or abs(score) > abs(best["_score"]):
            best = {
                "ticker": ticker,
                "label": _TICKER_LABELS.get(ticker, ticker),
                "confluence_direction": confluence.get("direction"),
                "confluence_confidence_pct": confluence.get("confidence_pct"),
                "last_close": tech.get("last_close"),
                "_score": score,
            }
    if best:
        best.pop("_score", None)
    return best


def _compute_nine_categories() -> Dict:
    pulse = _compute_pulse()
    trending = get_trending_for_country("US")
    signals = _compute_all_signals()

    # Sector-rotation leaderboard already sorted strongest-first by
    # _compute_pulse() -- reframe the same real data as "fund flow".
    basket_sorted = [b for b in pulse.get("basket", []) if b.get("available")]
    flow_in = basket_sorted[0] if basket_sorted else None
    flow_out = basket_sorted[-1] if len(basket_sorted) > 1 else None

    result = {
        "fund_flow": {
            "flow_in": flow_in,
            "flow_out": flow_out,
        } if basket_sorted else None,
        "sentiment": {
            "overall_sentiment": pulse.get("overall_sentiment"),
            "overall_score": pulse.get("overall_score"),
            "confidence_pct": pulse.get("confidence_pct"),
            "volatility_desc": pulse.get("volatility_desc"),
        },
        "trending": {
            "country": trending.get("country"),
            "assets": trending.get("stocks", [])[:5],
        },
        "fastest_growth": _compute_fastest_growth(),
        "best_opportunity": signals[0] if signals else None,
        "highest_yield": _compute_highest_yield(),
        "long_term": _compute_best_at_timeframe(
            _TIMEFRAME_SCAN["long_term"]["period"], _TIMEFRAME_SCAN["long_term"]["interval"]
        ),
        "mid_term": _compute_best_at_timeframe(
            _TIMEFRAME_SCAN["mid_term"]["period"], _TIMEFRAME_SCAN["mid_term"]["interval"]
        ),
        "short_term": _compute_best_at_timeframe(
            _TIMEFRAME_SCAN["short_term"]["period"], _TIMEFRAME_SCAN["short_term"]["interval"]
        ),
        "data_source": "即市技術分析（真實價格數據，非AI猜測）",
        "disclaimer": "呢個係整體市場技術面參考，唔係投資建議。",
    }
    return result


@router.get("/opportunity-categories")
def opportunity_categories():
    global _nine_cat_cache, _nine_cat_cache_time

    now = time.time()
    if _nine_cat_cache is not None and (now - _nine_cat_cache_time) < _NINE_CAT_CACHE_TTL_SECONDS:
        return {**_nine_cat_cache, "cached": True}

    result = _compute_nine_categories()
    _nine_cat_cache = result
    _nine_cat_cache_time = now
    return {**result, "cached": False}
