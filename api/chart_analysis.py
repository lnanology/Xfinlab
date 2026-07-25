import base64
import binascii
import hashlib
import json
import re
import time
from fastapi import APIRouter

from ai.ai_router import get_ai_response, get_vision_response
from services.technical_analysis_service import get_technical_analysis, get_multi_timeframe_analysis

router = APIRouter()

# --- Security limits ---
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB, after base64 decoding

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

# --- AI response cache (Security & Operations Layer, Phase 4 -- cost-free
# version) ---
# Keyed on a hash of the actual image bytes + symbol, so an IDENTICAL
# repeated request (same screenshot, same symbol -- e.g. a double-click, a
# page refresh, or a user re-checking the same chart minutes later) skips
# the paid vision-model call entirely and returns the prior result. This is
# a plain in-memory dict rather than Redis: same reasoning as the rate
# limiter in backend/main.py -- we're a single Railway instance today, so
# no shared-cache infra is needed yet, and a cache MISS always falls back
# to a normal live call, so correctness never depends on the cache being
# warm. Would need to move to Redis only if we ever scale to multiple
# instances.
_AI_RESPONSE_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL_SECONDS = 600  # 10 minutes
_CACHE_MAX_ENTRIES = 500  # simple cap so this can never grow unbounded


def _cache_key(raw_bytes: bytes, symbol: str) -> str:
    h = hashlib.sha256()
    h.update(raw_bytes)
    h.update(symbol.encode("utf-8"))
    return h.hexdigest()


def _cache_get(key: str):
    entry = _AI_RESPONSE_CACHE.get(key)
    if not entry:
        return None
    ts, result = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _AI_RESPONSE_CACHE.pop(key, None)
        return None
    return result


def _cache_set(key: str, result: dict) -> None:
    if len(_AI_RESPONSE_CACHE) >= _CACHE_MAX_ENTRIES:
        # Evict the oldest entry rather than letting the dict grow forever.
        oldest_key = min(_AI_RESPONSE_CACHE, key=lambda k: _AI_RESPONSE_CACHE[k][0])
        _AI_RESPONSE_CACHE.pop(oldest_key, None)
    _AI_RESPONSE_CACHE[key] = (time.time(), result)

# Real file signatures ("magic bytes") for the formats we accept.
# We check the ACTUAL decoded bytes, not whatever mime_type the client claims.
MAGIC_SIGNATURES = {
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/webp": [b"RIFF"],  # followed by size(4 bytes) + "WEBP", checked separately below
}


def detect_real_mime_type(raw_bytes: bytes) -> str | None:
    """
    Identify the file type from its actual binary signature, ignoring
    whatever mime_type the client (browser) claims. This stops a renamed
    or mislabeled file from slipping through as if it were an image.
    """
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw_bytes.startswith(b"RIFF") and raw_bytes[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/chart-analysis")
async def chart_analysis(body: dict):
    """
    Real chart image analysis using a vision-capable AI model.

    Expects:
        image: base64-encoded image data (no "data:" prefix)
        mime_type: image MIME type, e.g. "image/png" (advisory only — verified server-side)
        symbol: optional ticker/stock name for context

    Security notes:
        - We never write the uploaded image to disk, and never open it with
          a local image-processing library (Pillow/ImageMagick etc.) — it is
          only base64-encoded and forwarded to the vision API. This avoids
          the classic "malicious image exploits local image decoder" attack
          surface entirely.
        - We still enforce a size cap and verify the real file signature
          before doing anything else, so we reject bad/oversized payloads
          as early and cheaply as possible.
    """
    image_base64 = body.get("image")
    symbol = body.get("symbol", "")
    token = body.get("token")

    if not image_base64:
        return {
            "status": "error",
            "message": "冇收到圖片，請重新上傳K線圖。"
        }

    # --- Layer 1: decode + size check ---
    try:
        raw_bytes = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError):
        return {
            "status": "error",
            "message": "圖片格式無效，請重新上傳。"
        }

    if len(raw_bytes) > MAX_IMAGE_BYTES:
        return {
            "status": "error",
            "message": "圖片檔案過大（上限8MB），請上傳較細嘅圖片。"
        }

    if len(raw_bytes) == 0:
        return {
            "status": "error",
            "message": "圖片內容為空，請重新上傳。"
        }

    # --- Layer 2: verify the REAL file signature, not the client's claim ---
    real_mime_type = detect_real_mime_type(raw_bytes)
    if not real_mime_type:
        return {
            "status": "error",
            "message": "僅支援 JPG / PNG / WebP 格式嘅圖片，請重新上傳。"
        }

    # --- Cache check: identical (image bytes + symbol) within TTL skips
    # the paid AI vision call entirely. ---
    cache_key = _cache_key(raw_bytes, symbol)
    cached_result = _cache_get(cache_key)
    if cached_result is not None:
        return {"status": "ok", "data": {**cached_result, "cached": True}}

    # --- Try to get REAL market data first (if a symbol was supplied) ---
    # This is the Chart Analysis MVP: numeric levels (支撐/阻力/RSI/MACD/
    # Fibonacci) come from real historical OHLC data, not from an AI
    # "eyeballing" a screenshot. The AI is only asked to do what a human eye
    # is actually needed for: visual pattern recognition.
    tech = None
    if symbol:
        tech = get_technical_analysis(symbol)
        if tech and "error" in tech:
            tech = None  # fall back to AI-only flow below, silently

    if tech:
        prompt = (
            "你是專業技術分析師，正在觀察一張真實嘅K線圖截圖，"
            f"股票代號：{symbol}。\n\n"
            "以下係用真實歷史股價數據（唔係AI估計）精確計算出嚟嘅數值，"
            "你唔需要、亦都唔應該再自己估呢啲數字：\n"
            f"- 現價：{tech['last_close']}\n"
            f"- 趨勢（相對MA50）：{tech['trend']}\n"
            f"- RSI(14)：{tech['rsi']}\n"
            f"- MACD：{tech['macd']['trend']}（柱狀圖 {tech['macd']['histogram']}）\n"
            f"- 支撐位：{tech['support']['level'] if tech['support'] else '未偵測到'}\n"
            f"- 阻力位：{tech['resistance']['level'] if tech['resistance'] else '未偵測到'}\n"
            f"- 0.618 Fibonacci回調位：{tech['fibonacci_0618']['level_0618'] if tech['fibonacci_0618'] else '未偵測到'}\n"
            f"- 成交量：{tech['volume_desc']}\n"
            f"- 綜合訊號評分（Confluence）：{tech['confluence']['direction']}"
            f"（分數{tech['confluence']['score']}，信心{tech['confluence']['confidence']}）\n"
            f"  睇多訊號：{'、'.join(tech['confluence']['bullish_signals']) or '無'}\n"
            f"  睇淡訊號：{'、'.join(tech['confluence']['bearish_signals']) or '無'}\n\n"
            "你嘅任務淨係兩樣：\n"
            "1. 純粹用眼睇圖，辨識圖表入面嘅視覺型態（雙頂/雙底/頭肩頂/頭肩底/三角收斂/突破回測/"
            "0.618回調結構/旗形/尖旗形/通道/矩形整理/杯柄形/菱形/擴散形/ABC修正浪/缺口/島型反轉）。"
            "如果張圖睇唔清楚某個型態，誠實答「不可能」或者「不明」，唔好靠估。\n"
            "2. 結合上面提供嘅真實數據 + Confluence評分 + 你睇到嘅視覺型態，畀出簡短風險提示同建議，"
            "如果你睇到嘅型態同Confluence評分方向一致，要喺建議入面講明「型態同數據訊號一致」；"
            "如果矛盾，要講明邊樣同邊樣有衝突，唔好扮冇睇到。\n"
            "唔好自己再估支撐位/阻力位/RSI/MACD數值，一律以上面提供嘅真實數據為準。\n"
            "每個欄位答案要精簡，唔好超過20隻字。\n\n"
            "只回覆一個JSON物件，唔好加任何其他文字、唔好加markdown、唔好加解釋：\n"
            "{\n"
            '  "patterns": {\n'
            '    "p_double_top": "可能/不可能",\n'
            '    "p_double_bottom": "可能/不可能",\n'
            '    "p_head_shoulder_top": "可能/不可能",\n'
            '    "p_head_shoulder_bottom": "可能/不可能",\n'
            '    "p_triangle": "可能/不可能",\n'
            '    "p_breakback": "可能/不可能",\n'
            '    "p_0618": "可能/不可能",\n'
            '    "p_flag": "可能/不可能",\n'
            '    "p_pennant": "可能/不可能",\n'
            '    "p_channel": "可能/不可能",\n'
            '    "p_rectangle": "可能/不可能",\n'
            '    "p_cup_handle": "可能/不可能",\n'
            '    "p_diamond": "可能/不可能",\n'
            '    "p_broadening": "可能/不可能",\n'
            '    "p_abc": "可能/不可能",\n'
            '    "p_gap": "可能/不可能",\n'
            '    "p_island": "可能/不可能"\n'
            '  },\n'
            '  "risk": "簡短風險提示，15隻字內",\n'
            '  "recommendation": "簡短建議，15隻字內"\n'
            "}"
        )
        max_tokens = 1800
    else:
        prompt = (
            "你是專業技術分析師，正在觀察一張真實嘅K線圖截圖。"
            f"{'股票代號：' + symbol if symbol else ''}\n\n"
            "重要規則：\n"
            "1. 只可以根據你喺圖片入面實際睇到嘅刻度、數字、線條嚟分析，唔可以估計或者作大約數值。\n"
            "2. 支撐位/阻力位要參考圖表Y軸嘅實際刻度數字，逐格對照，唔好隨便估一個接近嘅數。\n"
            "3. 如果睇唔清楚、圖片太細或者冇顯示某項資訊（例如RSI、MACD），"
            "就照實寫「圖中未能清楚辨識」或者「圖中未顯示」，唔好亂up答案。\n"
            "4. 檢查圖表下方有冇獨立嘅指標窗格（RSI通常0-100，MACD通常有柱狀圖+兩條線），"
            "如果有先評論，如果冇就講明冇顯示。\n"
            "5. 每個欄位嘅答案要精簡，唔好超過15隻字，唔好寫長句子。\n\n"
            "用繁體中文提供以下分析，只回覆一個JSON物件，唔好加任何其他文字，"
            "唔好加markdown、唔好加解釋，只回覆單一個完整JSON：\n"
            "{\n"
            '  "trend": "上升/下降/橫盤",\n'
            '  "support": "價格數字或『未能辨識』",\n'
            '  "resistance": "價格數字或『未能辨識』",\n'
            '  "volume": "簡短描述或『未顯示』",\n'
            '  "rsi": "數值+簡短描述或『未顯示』",\n'
            '  "macd": "簡短描述或『未顯示』",\n'
            '  "patterns": {\n'
            '    "p_double_top": "可能/不可能",\n'
            '    "p_double_bottom": "可能/不可能",\n'
            '    "p_head_shoulder_top": "可能/不可能",\n'
            '    "p_head_shoulder_bottom": "可能/不可能",\n'
            '    "p_triangle": "可能/不可能",\n'
            '    "p_breakback": "可能/不可能",\n'
            '    "p_0618": "可能/不可能",\n'
            '    "p_flag": "可能/不可能",\n'
            '    "p_pennant": "可能/不可能",\n'
            '    "p_channel": "可能/不可能",\n'
            '    "p_rectangle": "可能/不可能",\n'
            '    "p_cup_handle": "可能/不可能",\n'
            '    "p_diamond": "可能/不可能",\n'
            '    "p_broadening": "可能/不可能",\n'
            '    "p_abc": "可能/不可能",\n'
            '    "p_gap": "可能/不可能",\n'
            '    "p_island": "可能/不可能"\n'
            '  },\n'
            '  "risk": "簡短風險提示，15隻字內",\n'
            '  "recommendation": "簡短建議，15隻字內"\n'
            "}"
        )
        max_tokens = 3500

    from services.quota_middleware import check_token_budget, record_ai_token_usage
    user_id = check_token_budget(token)

    try:
        raw_answer = get_vision_response(prompt, image_base64, real_mime_type, max_tokens=max_tokens)
        record_ai_token_usage(user_id)
        answer = raw_answer.replace("```json", "").replace("```", "").strip()
        start = answer.find("{")
        end = answer.rfind("}") + 1
        if start != -1 and end > start:
            answer = answer[start:end]

        # AI models sometimes leave a trailing comma before } or ] which
        # breaks strict JSON parsing — strip those before parsing.
        answer_cleaned = re.sub(r",\s*([}\]])", r"\1", answer)

        try:
            ai_result = json.loads(answer_cleaned)
        except json.JSONDecodeError as e:
            # Temporary debug aid: include a snippet of what the AI actually
            # returned so we can see exactly what's malformed.
            snippet = answer_cleaned[:300]
            return {
                "status": "error",
                "message": f"AI回覆格式有問題：{str(e)} | 原始回覆片段：{snippet}"
            }

        # --- Merge: real market data (numeric levels) + AI (visual patterns) ---
        if tech:
            result = {
                "trend": tech["trend"],
                "support": tech["support"]["level"] if tech["support"] else "未偵測到",
                "resistance": tech["resistance"]["level"] if tech["resistance"] else "未偵測到",
                "volume": tech["volume_desc"],
                # Real value, needed by the frontend's unified "Decision
                # Report" footer to compute a RiskDNA(TM) label using the
                # SAME RiskEngine.assess(volume_ratio*15) formula already
                # used in api/hero_showcase.py -- was previously computed
                # here but never forwarded to the client.
                "volume_ratio": tech.get("volume_ratio"),
                "rsi": tech["rsi"],
                "macd": tech["macd"]["trend"],
                "fibonacci_0618": tech["fibonacci_0618"]["level_0618"] if tech["fibonacci_0618"] else None,
                "confluence": tech["confluence"],
                # Phase 1 Decision Engine upgrade -- passed through as-is
                # (already None when there's no clear bias/real level to
                # anchor on; see _decision_levels()'s own no-fabrication
                # guards in technical_analysis_service.py).
                "decision_levels": tech.get("decision_levels"),
                "patterns": ai_result.get("patterns", {}),
                "risk": ai_result.get("risk", ""),
                "recommendation": ai_result.get("recommendation", ""),
                "data_source": "real_market_data+ai_vision_patterns",
            }
        else:
            result = ai_result
            result["data_source"] = "ai_vision_only"

        _cache_set(cache_key, result)
        return {"status": "ok", "data": {**result, "cached": False}}
    except Exception as e:
        return {
            "status": "error",
            "message": f"分析失敗，請重試：{str(e)}"
        }


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
def chart_search(symbol: str, period: str = "6mo", interval: str = "1d"):
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

    cache_key = f"{symbol}|{period}|{interval}"
    cached = _ttl_cache_get(_CHART_SEARCH_CACHE, cache_key, _CHART_SEARCH_CACHE_TTL_SECONDS)
    if cached is not None:
        return {"status": "ok", "data": {**cached, "cached": True}}

    tech = get_technical_analysis(symbol, period, interval)
    if not tech or "error" in tech:
        return {"status": "error", "message": (tech or {}).get("error") or f"攞唔到 {symbol} 嘅數據"}

    _ttl_cache_set(_CHART_SEARCH_CACHE, cache_key, tech, _CHART_SEARCH_CACHE_MAX_ENTRIES)
    return {"status": "ok", "data": {**tech, "cached": False}}


@router.get("/chart-search/{symbol}/commentary")
def chart_search_commentary(symbol: str, period: str = "6mo", interval: str = "1d", token: str = None):
    """
    Optional, user-triggered plain-text AI summary of the real numeric
    data above. Deliberately a separate, lazy endpoint rather than being
    bundled into /chart-search -- the default search-and-chart flow costs
    zero LLM calls; this only runs when the user explicitly clicks
    "Generate AI commentary". Text-only completion (get_ai_response), not
    vision -- there's no screenshot in this flow, so there's nothing for a
    vision model to look at; it's purely writing up numbers that were
    already computed from real market data.
    """
    symbol = (symbol or "").strip().upper()
    if not symbol or not _SYMBOL_RE.match(symbol):
        return {"status": "error", "message": "代號格式無效，請重新輸入。"}

    cache_key = f"{symbol}|{period}|{interval}"
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
        "用繁體中文，將以上數據寫成一段簡短、易讀嘅文字解讀（80字以內），"
        "需要包含關鍵風險提示，唔好自己估任何新數字，一律以上面提供嘅真實數據為準。"
        "只回覆純文字，唔好加JSON、唔好加markdown、唔好加任何其他文字。"
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
def chart_search_multi_timeframe(symbol: str):
    """
    Optional, user-triggered multi-timeframe alignment check -- compares
    Weekly/Daily/1-Hour trend + confluence direction for the same symbol.
    Not called automatically on every search since it costs 3x the
    historical-data fetches of a normal /chart-search call.
    """
    symbol = (symbol or "").strip().upper()
    if not symbol or not _SYMBOL_RE.match(symbol):
        return {"status": "error", "message": "代號格式無效，請重新輸入。"}

    cached = _ttl_cache_get(_MTF_CACHE, symbol, _MTF_CACHE_TTL_SECONDS)
    if cached is not None:
        return {"status": "ok", "data": {**cached, "cached": True}}

    result = get_multi_timeframe_analysis(symbol)
    if not result:
        return {"status": "error", "message": f"攞唔到 {symbol} 嘅多時間框架數據"}

    _ttl_cache_set(_MTF_CACHE, symbol, result, _MTF_CACHE_MAX_ENTRIES)
    return {"status": "ok", "data": {**result, "cached": False}}
