"""
Smart AI Router -- takes whatever free-text a visitor types into the
homepage's single "tell me what you're thinking" input box and figures
out which of XFINLAB's 11 Engine pages it should send them to (plus
any ticker mentioned), so one box can stand in for "I don't know which
tool to use, just answer my question."

Two-stage design, same "local-first, AI-supplement" philosophy already
used by js/autocomplete.js's live search fusion:

  1. classify_fast() -- pure regex/keyword matching, no network call,
     instant. Handles the common cases: a bare ticker ("AAPL"), or a
     ticker plus an obvious keyword ("AAPL 走勢圖" -> chart-analysis,
     "比較 TSLA 同 FORD" -> company-compare, "BTC 會唔會跌" ->
     probability-scan, etc).
  2. classify_ai() -- fallback for anything ambiguous or too
     conversational for keyword matching ("依家邊隻股份值博率最高？").
     Uses the site's existing AI router (ai/ai_router.py) so it shares
     the same GROQ/DeepSeek/Claude provider switch as every other
     AI-backed feature -- no new API key/dependency introduced.

Every intent maps to a real page + the exact query-string param that
page already reads on load (see each page's "Share System" /
DOMContentLoaded block) -- reused, not reinvented, so a routed link
behaves identically to a shared link a user pastes in manually.
"""
import json
import re

# intent_key -> (page, query param name used by that page's own
# DOMContentLoaded auto-run block, human label for the AI prompt)
INTENT_MAP = {
    "chart":       {"page": "chart-analysis.html",  "param": "symbol",    "label": "chart pattern / technical chart analysis"},
    "compare":     {"page": "company-compare.html",  "param": "companies", "label": "compare multiple companies/tickers"},
    "probability": {"page": "probability-scan.html", "param": "ticker",   "label": "bullish/bearish probability of one ticker"},
    "anomaly":     {"page": "anomaly.html",           "param": "ticker",   "label": "sudden volume/price spike detection"},
    "portfolio":   {"page": "portfolio.html",         "param": None,       "label": "portfolio allocation / diversification"},
    "news":        {"page": "news-denoise.html",      "param": "query",   "label": "news summary / sentiment on a ticker or topic"},
    "stress":      {"page": "stress-lab.html",        "param": None,       "label": "black-swan stress test / crash scenario"},
    "screener":    {"page": "screener.html",          "param": None,       "label": "screen/filter for stocks matching criteria"},
    "chat":        {"page": "chat.html",              "param": "q",        "label": "open-ended conversational question"},
    "dashboard":   {"page": "dashboard.html",         "param": None,       "label": "watchlist / personal dashboard"},
    # "analysis" is deliberately NOT a redirect -- it means "just a bare
    # ticker, no other intent", which the homepage's own inline demo
    # card already handles (see index.html's runDemo()). Routing code
    # should treat this as "stay on homepage".
    "analysis":    {"page": None,                     "param": None,       "label": "quick score/analysis of one ticker"},
}

# Keyword -> intent, checked as case-insensitive substrings. Ordered so
# more specific multi-word phrases are checked before generic ones.
_KEYWORDS = [
    ("compare", ["比較", "對比", "同邊隻好", "vs", "compare", "which is better"]),
    ("chart", ["圖表", "k線", "k线", "型態", "走勢圖", "chart", "candlestick", "pattern"]),
    ("anomaly", ["異常", "暴增", "爆量", "反常", "volume spike", "anomaly", "unusual volume"]),
    ("probability", ["機率", "概率", "會唔會升", "會唔會跌", "bullish", "bearish", "probability", "會升定跌"]),
    ("portfolio", ["配置", "持倉", "portfolio", "allocation", "分散投資"]),
    ("stress", ["壓力測試", "黑天鵝", "stress test", "崩盤", "crash scenario"]),
    ("screener", ["篩選", "選股", "screener", "screen for", "find stocks"]),
    ("news", ["新聞", "消息", "news", "sentiment"]),
    ("dashboard", ["自選股", "watchlist", "dashboard"]),
]

# Same ticker-format guard used elsewhere (api/anomaly.py, api/chart_analysis.py).
# Includes "^" (2026-07-25 fix, see chart_analysis.py's _SYMBOL_RE comment)
# so world indices/VIX/Treasury-yield tickers (^HSI, ^GSPC, ^VIX, ^TNX etc.)
# aren't rejected.
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-=^]{1,12}$")


def _extract_ticker(text: str):
    """Pull the first token that looks like a ticker out of free text.
    Deliberately conservative (only bare alphanumeric tokens, 1-12
    chars) -- false negatives (missing a ticker) are fine, since the
    page the user lands on still has its own search box; false
    positives (treating a random word as a ticker) are worse."""
    for token in re.findall(r"[A-Za-z0-9.\-^]{1,12}", text):
        candidate = token.upper().strip(".-")
        if candidate and _SYMBOL_RE.match(candidate) and any(c.isalnum() for c in candidate):
            # Skip obviously-not-a-ticker all-lowercase common words that
            # happen to be short (e.g. "vs", "the") -- require at least
            # one digit OR be short+uppercase-ish looking already.
            if candidate.isalpha() and len(candidate) <= 2:
                continue
            return candidate
    return None


def classify_fast(query: str):
    """Regex/keyword-only pass. Returns a result dict, or None if the
    query doesn't clearly match any known intent (caller should then
    fall back to classify_ai)."""
    q = (query or "").strip()
    if not q:
        return None

    ticker = _extract_ticker(q)
    lower = q.lower()

    for intent, keywords in _KEYWORDS:
        if any(kw in q or kw in lower for kw in keywords):
            return {"intent": intent, "ticker": ticker}

    # No intent keyword found. If the whole input is basically just a
    # bare ticker (nothing else meaningful typed), that's the
    # "analysis" intent -- handled inline by the homepage's own demo
    # card, not a redirect.
    stripped = re.sub(r"[^A-Za-z0-9.\-]", "", q)
    if ticker and stripped.upper() == ticker:
        return {"intent": "analysis", "ticker": ticker}

    return None


def classify_ai(query: str):
    """AI fallback for anything classify_fast() couldn't confidently
    resolve -- typically a full natural-language question. Returns the
    same {"intent", "ticker"} shape, defaulting to "chat" (the
    conversational catch-all page) if the model's answer is unusable
    for any reason."""
    from ai.ai_router import get_ai_response

    intents_desc = "\n".join(f'- "{k}": {v["label"]}' for k, v in INTENT_MAP.items())
    prompt = (
        "Classify the user's query into exactly one of these intent keys, and "
        "extract any stock/crypto ticker symbol mentioned (or null if none):\n"
        f"{intents_desc}\n\n"
        f'User query: "{query}"\n\n'
        'Respond with ONLY a JSON object, no other text: '
        '{"intent": "<one of the keys above>", "ticker": "<TICKER or null>"}'
    )

    try:
        raw = get_ai_response(prompt, max_tokens=100)
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return {"intent": "chat", "ticker": None}
        parsed = json.loads(match.group(0))
        intent = parsed.get("intent")
        if intent not in INTENT_MAP:
            intent = "chat"
        ticker = parsed.get("ticker")
        if ticker and (not isinstance(ticker, str) or not _SYMBOL_RE.match(ticker.upper())):
            ticker = None
        return {"intent": intent, "ticker": (ticker.upper() if ticker else None)}
    except Exception:
        return {"intent": "chat", "ticker": None}


def route_query(query: str):
    """Full pipeline: fast path first, AI fallback second. Returns:
    {
      "status": "ok",
      "intent": str,
      "ticker": str | None,
      "stay_on_homepage": bool,  # True for "analysis" intent
      "url": str | None,         # relative page URL to navigate to, None if staying
    }
    """
    result = classify_fast(query)
    used_ai = False
    if result is None:
        result = classify_ai(query)
        used_ai = True

    intent = result.get("intent", "chat")
    ticker = result.get("ticker")
    meta = INTENT_MAP.get(intent, INTENT_MAP["chat"])

    if meta["page"] is None:
        return {
            "status": "ok",
            "intent": intent,
            "ticker": ticker,
            "stay_on_homepage": True,
            "url": None,
            "used_ai": used_ai,
        }

    url = meta["page"]
    if meta["param"] and ticker:
        url += f"?{meta['param']}={ticker}"
    elif meta["param"] == "q" and query:
        # chat.html's "q" param carries the whole free-text question,
        # not just a ticker.
        from urllib.parse import quote
        url += f"?q={quote(query)}"

    return {
        "status": "ok",
        "intent": intent,
        "ticker": ticker,
        "stay_on_homepage": False,
        "url": url,
        "used_ai": used_ai,
    }
