"""
Common CFD/futures index shorthand -> human-readable label.

Root-cause fix for: typing "HK50" into AI Chat gets treated as an
unrecognized string instead of the Hang Seng Index futures -- there was
no lookup anywhere in the repo for this popular CFD-broker naming
convention (normalizeGlobalTicker in js/autocomplete.js only handles
numeric HK codes and a small crypto whitelist; js/autocomplete.js's
ASSETS table uses CME/Yahoo-style names like ^HSI/HSIF, not CFD
shorthand). This is intentionally small and index/futures-only --
regular equity tickers (AAPL, 0700.HK, etc.) are already handled
elsewhere and don't need this.
"""
import re

# CFD-broker shorthand (as commonly seen on IG/OANDA/Pepperstone-style
# platforms) -> (Chinese label, English label). Kept as a flat dict so
# detect_index_futures() can do one case-insensitive word-boundary scan.
INDEX_FUTURES_SHORTHAND = {
    "HK50": ("恒生指數期貨（Hang Seng Index Futures）", "Hang Seng Index futures"),
    "US30": ("道瓊斯指數期貨（Dow Jones Futures）", "Dow Jones Industrial Average futures"),
    "NAS100": ("納斯達克100指數期貨（Nasdaq 100 Futures）", "Nasdaq 100 futures"),
    "US100": ("納斯達克100指數期貨（Nasdaq 100 Futures）", "Nasdaq 100 futures"),
    "SPX500": ("標普500指數期貨（S&P 500 Futures）", "S&P 500 futures"),
    "US500": ("標普500指數期貨（S&P 500 Futures）", "S&P 500 futures"),
    "GER40": ("德國DAX指數期貨（DAX Futures）", "DAX (Germany 40) futures"),
    "DE40": ("德國DAX指數期貨（DAX Futures）", "DAX (Germany 40) futures"),
    "UK100": ("英國富時100指數期貨（FTSE 100 Futures）", "FTSE 100 futures"),
    "JPN225": ("日經225指數期貨（Nikkei 225 Futures）", "Nikkei 225 futures"),
    "JP225": ("日經225指數期貨（Nikkei 225 Futures）", "Nikkei 225 futures"),
    "AUS200": ("澳洲標普200指數期貨（ASX 200 Futures）", "ASX 200 futures"),
    "FRA40": ("法國CAC40指數期貨（CAC 40 Futures）", "CAC 40 futures"),
    "EU50": ("歐洲STOXX50指數期貨（Euro Stoxx 50 Futures）", "Euro Stoxx 50 futures"),
    "CHINA50": ("富時中國A50指數期貨（FTSE China A50 Futures）", "FTSE China A50 futures"),
    # 2026-07-24 follow-up ("CH50 呢D 搜不到"): CH50 is the same FTSE China
    # A50 futures product as CHINA50 above, just a shorter broker-code
    # spelling some CFD platforms use -- added as its own key (not merely
    # an alias) so detect_index_futures()'s single case-insensitive scan
    # still catches it directly.
    "CH50": ("富時中國A50指數期貨（FTSE China A50 Futures）", "FTSE China A50 futures"),
    "USOIL": ("美國WTI原油期貨（WTI Crude Oil Futures）", "WTI crude oil futures"),
    "UKOIL": ("英國布蘭特原油期貨（Brent Crude Oil Futures）", "Brent crude oil futures"),
}

_PATTERN = re.compile(
    # Plain \b breaks here: Python's Unicode-aware \w treats CJK
    # characters as "word" characters too, so e.g. "下HK50同" (CJK
    # immediately touching the shorthand) has no \w/\W boundary at all
    # between "下" and "H" and the match is silently skipped. Use
    # explicit ASCII-alnum lookaround instead -- only reject the match
    # if it's glued to *another Latin letter/digit* (e.g. "SHK50X"),
    # CJK/punctuation/whitespace/string-edges on either side are fine.
    r"(?<![A-Za-z0-9])(" + "|".join(re.escape(k) for k in INDEX_FUTURES_SHORTHAND) + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def detect_index_futures(text: str):
    """Scan free text for known CFD index/futures shorthand. Returns a
    list of (matched_text, zh_label, en_label) tuples, de-duplicated by
    the canonical uppercase key, in first-seen order. Never raises."""
    if not text:
        return []
    seen = set()
    out = []
    try:
        for m in _PATTERN.finditer(text):
            key = m.group(1).upper()
            if key in seen:
                continue
            seen.add(key)
            zh, en = INDEX_FUTURES_SHORTHAND[key]
            out.append((m.group(1), zh, en))
    except Exception:
        return []
    return out


def build_context_note(text: str) -> str:
    """Build a short clarifying note to prepend to an AI prompt when the
    query contains recognized index/futures shorthand, so the model
    doesn't have to guess what e.g. "HK50" refers to. Returns '' if
    nothing recognized."""
    matches = detect_index_futures(text)
    if not matches:
        return ""
    lines = [f"「{raw}」係{zh}，唔係普通股票代號。" for raw, zh, _en in matches]
    return "背景資訊：" + " ".join(lines) + "\n\n"
