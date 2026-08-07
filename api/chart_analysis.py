import re
import time
from fastapi import APIRouter

from ai.ai_router import get_ai_response
from services.technical_analysis_service import get_technical_analysis, get_multi_timeframe_analysis
from services.i18n import ai_language_instruction

router = APIRouter()

# Ticker symbols only -- letters, digits, dot, dash, equals, caret (covers
# AAPL, 0700.HK, ES=F, BTC-USD, ^HSI/^GSPC/^DJI/^VIX/^TNX etc.). Validated
# BEFORE anything touches yfinance/Alpaca so junk input is rejected
# cheaply, before any network call is made.
#
# 2026-07-25 fix ("期貨無既... 指 債 ETF... 所有資產可見"): this regex was
# missing "^", the standard yfinance prefix for every world index (^HSI,
# ^GSPC, ^DJI, ^IXIC, ^N225, ^FTSE...), VIX (^VIX), and Treasury-yield
# "bond" tickers (^TNX/^TYX/^FVX) -- so every one of those, whether typed
# directly or auto-filled from autocomplete.js's own `api` field (which
# already uses these exact ^-prefixed tickers for HK50/US30/SPX500/etc),
# was silently rejected here with "代號格式無效" before ever reaching
# yfinance. api/backtest.py's own _SYMBOL_RE already included "^" --
# this brings the other two copies in line with it.
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-=^]{1,12}$")

# 2026-08-08 removal (AJ, chart-analysis.html's upload-screenshot mode:
# "AI Chart Analysis 上傳截圖 收起 唔用" -- confirmed via clarifying
# question: fully remove the feature, not just hide it): this file used
# to have a POST /chart-analysis endpoint here that took a base64-encoded
# screenshot + optional symbol, ran it through a vision-capable AI model
# (ai/ai_router.py's get_vision_response) for visual pattern recognition,
# and merged that with real get_technical_analysis() numbers when a
# symbol was supplied. Along with it: an 8MB size cap, a magic-bytes file-
# signature check (detect_real_mime_type), and an image-bytes+symbol
# keyed AI-response cache -- all upload-specific, all removed together
# since nothing else in this file (or the rest of the codebase -- grepped
# for get_vision_response, detect_real_mime_type, _AI_RESPONSE_CACHE) used
# them. The GET /chart-search/* ticker-search endpoints below are
# untouched -- they already do real-data pattern detection via services/
# chart_pattern_service.py without needing a screenshot at all (task
# #463-468), so search mode's Pattern Details panel keeps working exactly
# as before.


# --- Global-ticker-search flow: real OHLC + indicators, no screenshot ---
# needed at all. Separate in-memory TTL cache from the image-analysis one
# above, keyed on (symbol, period, interval) rather than image bytes,
# since there's no image here -- a popular ticker searched repeatedly
# within the TTL window reuses the same result instead of re-hitting
# Alpaca/yfinance every time.
_CHART_SEARCH_CACHE: dict[str, tuple[float, dict]] = {}
_CHART_SEARCH_CACHE_TTL_SECONDS = 300  # 5 minutes
_CHART_SEARCH_CACHE_MAX_ENTRIES = 300

# Separate cache for the optional AI text commentary (see below) -- longer
# TTL since it's prose summarising numbers that don't need to be quite as
# fresh as the chart itself, and it's only ever populated on demand.
_COMMENTARY_CACHE: dict[str, tuple[float, str]] = {}
_COMMENTARY_CACHE_TTL_SECONDS = 900  # 15 minutes
_COMMENTARY_CACHE_MAX_ENTRIES = 300


def _ttl_cache_get(store: dict, key: str, ttl: int):
    entry = store.get(key)
    if not entry:
        return None
    ts, value = entry
    if time.time() - ts > ttl:
        store.pop(key, None)
        return None
    return value


def _ttl_cache_set(store: dict, key: str, value, max_entries: int) -> None:
    if len(store) >= max_entries:
        oldest_key = min(store, key=lambda k: store[k][0])
        store.pop(oldest_key, None)
    store[key] = (time.time(), value)


@router.get("/chart-search/{symbol}")
def chart_search(symbol: str, period: str = "6mo", interval: str = "1d", lang: str = None):
    """
    Global-ticker-search chart analysis -- the "type a ticker, no
    screenshot" flow. Returns real OHLC bars (for client-side candlestick
    rendering) plus the same real-data indicators the image-upload flow
    above already computes (support/resistance/RSI/MACD/Fibonacci/
    confluence). AI vision is never invoked here -- there's no image to
    look at, and the numeric levels already come straight from real
    historical data, same as always.
    """
    symbol = (symbol or "").strip().upper()
    if not symbol or not _SYMBOL_RE.match(symbol):
        return {"status": "error", "message": "代號格式無效，請重新輸入。"}

    # 2026-07-25 fix (task #409): cache key includes lang so an English
    # request never serves back a Chinese-cached response (or vice versa)
    # -- get_technical_analysis's translation happens once per fetch, not
    # per read, so the cache would otherwise "freeze" whichever language
    # requested it first for every other language until the TTL expires.
    cache_key = f"{symbol}|{period}|{interval}|{lang or ''}"
    cached = _ttl_cache_get(_CHART_SEARCH_CACHE, cache_key, _CHART_SEARCH_CACHE_TTL_SECONDS)
    if cached is not None:
        return {"status": "ok", "data": {**cached, "cached": True}}

    tech = get_technical_analysis(symbol, period, interval, lang=lang)
    if not tech or "error" in tech:
        return {"status": "error", "message": (tech or {}).get("error") or f"攞唔到 {symbol} 嘅數據"}

    _ttl_cache_set(_CHART_SEARCH_CACHE, cache_key, tech, _CHART_SEARCH_CACHE_MAX_ENTRIES)
    return {"status": "ok", "data": {**tech, "cached": False}}


@router.get("/chart-search/{symbol}/commentary")
def chart_search_commentary(
    symbol: str, period: str = "6mo", interval: str = "1d", token: str = None, lang: str = None
):
    """
    Optional, user-triggered plain-text AI summary of the real numeric
    data above. Deliberately a separate, lazy endpoint rather than being
    bundled into /chart-search -- the default search-and-chart flow costs
    zero LLM calls; this only runs when the user explicitly clicks
    "Generate AI commentary". Text-only completion (get_ai_response), not
    vision -- there's no screenshot in this flow, so there's nothing for a
    vision model to look at; it's purely writing up numbers that were
    already computed from real market data.

    2026-07-31 fix: this used to hard-force "用繁體中文" (Traditional
    Chinese) into the prompt regardless of the site's selected UI
    language -- same backend-hardcoded-language bug already fixed once
    for the screener prompt (task #317/#327) and once for
    historical_analog_service.py (task #530). Now accepts the same
    `lang` param the sibling /chart-search and /multi-timeframe endpoints
    on this router already take, and swaps in the shared
    ai_language_instruction(lang) helper (services/i18n.py) instead of a
    literal Chinese sentence -- same helper api/chat.py and
    api/ai_analysis.py's screener prompt already use, so this doesn't
    invent a second translation mechanism for the same concept.
    """
    symbol = (symbol or "").strip().upper()
    if not symbol or not _SYMBOL_RE.match(symbol):
        return {"status": "error", "message": "代號格式無效，請重新輸入。"}

    cache_key = f"{symbol}|{period}|{interval}|{lang or ''}"
    cached = _ttl_cache_get(_COMMENTARY_CACHE, cache_key, _COMMENTARY_CACHE_TTL_SECONDS)
    if cached is not None:
        return {"status": "ok", "data": {"commentary": cached, "cached": True}}

    tech = get_technical_analysis(symbol, period, interval)
    if not tech or "error" in tech:
        return {"status": "error", "message": (tech or {}).get("error") or f"攞唔到 {symbol} 嘅數據"}

    c = tech["confluence"]
    prompt = (
        "你是專業技術分析師，以下係用真實歷史股價數據計算出嚟嘅指標，"
        f"股票代號：{symbol}。\n\n"
        f"現價：{tech['last_close']}\n"
        f"趨勢（相對MA50）：{tech['trend']}\n"
        f"RSI(14)：{tech['rsi']}\n"
        f"MACD：{tech['macd']['trend']}\n"
        f"支撐位：{tech['support']['level'] if tech['support'] else '未偵測到'}\n"
        f"阻力位：{tech['resistance']['level'] if tech['resistance'] else '未偵測到'}\n"
        f"成交量：{tech['volume_desc']}\n"
        f"綜合訊號（Confluence）：{c['direction']}（分數{c['score']}，信心{c['confidence']}）\n"
        f"睇多訊號：{'、'.join(c['bullish_signals']) or '無'}\n"
        f"睇淡訊號：{'、'.join(c['bearish_signals']) or '無'}\n\n"
        "將以上數據寫成一段簡短、易讀嘅文字解讀（80字以內），"
        "需要包含關鍵風險提示，唔好自己估任何新數字，一律以上面提供嘅真實數據為準。"
        "只回覆純文字，唔好加JSON、唔好加markdown、唔好加任何其他文字。"
        f" {ai_language_instruction(lang)}"
    )
    from services.quota_middleware import check_token_budget, record_ai_token_usage
    user_id = check_token_budget(token)

    try:
        commentary = get_ai_response(prompt, max_tokens=400).strip()
        record_ai_token_usage(user_id)
    except Exception as e:
        return {"status": "error", "message": f"AI解讀生成失敗，請重試：{str(e)}"}

    _ttl_cache_set(_COMMENTARY_CACHE, cache_key, commentary, _COMMENTARY_CACHE_MAX_ENTRIES)
    return {"status": "ok", "data": {"commentary": commentary, "cached": False}}


# --- Phase 2 Multi-Timeframe Engine endpoint ---
# Separate cache from the main chart-search one -- this call fetches 3x
# the historical data (Weekly/Daily/1-Hour), so it's deliberately its own
# lazy, user-triggered endpoint rather than bundled into every search.
_MTF_CACHE: dict[str, tuple[float, dict]] = {}
_MTF_CACHE_TTL_SECONDS = 600  # 10 minutes
_MTF_CACHE_MAX_ENTRIES = 200


@router.get("/chart-search/{symbol}/multi-timeframe")
def chart_search_multi_timeframe(symbol: str, lang: str = None):
    """
    Optional, user-triggered multi-timeframe alignment check -- compares
    Weekly/Daily/1-Hour trend + confluence direction for the same symbol.
    Not called automatically on every search since it costs 3x the
    historical-data fetches of a normal /chart-search call.
    """
    symbol = (symbol or "").strip().upper()
    if not symbol or not _SYMBOL_RE.match(symbol):
        return {"status": "error", "message": "代號格式無效，請重新輸入。"}

    cache_key = f"{symbol}|{lang or ''}"
    cached = _ttl_cache_get(_MTF_CACHE, cache_key, _MTF_CACHE_TTL_SECONDS)
    if cached is not None:
        return {"status": "ok", "data": {**cached, "cached": True}}

    result = get_multi_timeframe_analysis(symbol, lang=lang)
    if not result:
        return {"status": "error", "message": f"攞唔到 {symbol} 嘅多時間框架數據"}

    _ttl_cache_set(_MTF_CACHE, symbol, result, _MTF_CACHE_MAX_ENTRIES)
    return {"status": "ok", "data": {**result, "cached": False}}
