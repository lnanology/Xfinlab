"""
Live global asset search -- uses yfinance's own Lookup class (which
manages Yahoo Finance's cookie/crumb session handshake internally, the
same session machinery already relied on everywhere else in this project
for real price/volume data) so the site's autocomplete isn't limited to
the ~230 tickers hand-curated in js/autocomplete.js's ASSETS array.

A hand-rolled raw HTTP call to Yahoo's search endpoint was tried first
and abandoned: Yahoo now requires a valid session cookie + "crumb"
token for most finance API calls (tightened over the last couple of
years specifically to block generic scrapers), which a plain requests.get
can't satisfy. yfinance already solves this internally, so we ride on
that instead of re-implementing cookie/crumb handling ourselves.

This is a *supplement* to the local curated list, not a replacement --
see js/autocomplete.js's fetchLiveAssetSearch()/renderResults(): local
results still render instantly (zero latency), live results merge in
a moment later once this endpoint responds.

2026-07-20 additions (global-search audit, "全世界搜查方向有咩要改善"):
  1. In-memory TTL cache -- this endpoint previously called yf.Lookup()
     fresh on EVERY request with zero caching, so the same popular query
     (e.g. "AAPL", "TSLA") from any number of different users all hit
     Yahoo's search index independently. That's both needless latency
     (every keystroke pays Yahoo's round-trip even for a query someone
     else just made) and the same class of risk that made task #204
     add a rate-limit/backoff helper elsewhere in this codebase after
     real Yahoo throttling was hit -- caching identical repeat queries
     is the cheapest way to cut outbound call volume before that becomes
     a problem here too. Kept small and simple (module-level dict, same
     pattern as services/fundamentals_service.py's _CACHE_TTL_DAYS) --
     not Redis, this app runs on one small dyno.
  2. Zero-result logging -- previously a query that returned nothing
     (or errored) was indistinguishable from one that worked, both here
     and in the frontend. Logging at least the query length/outcome
     (never the raw query text, to avoid accumulating a log of what
     users searched for) gives an honest signal for later prioritizing
     which tickers/aliases are worth adding to js/autocomplete.js's
     curated ASSETS list, instead of guessing.

Note: services/outbound_http.py's get_with_backoff() wrapper (task #204)
is NOT used here -- yfinance's yf.Lookup manages its own requests.Session
internally (that's the whole reason this module rides on yfinance instead
of a raw HTTP call, see above), so there's no bare requests.get() call
site here to swap in a drop-in wrapper. The TTL cache addresses the same
underlying risk (repeated outbound load) from a different angle instead.
"""
import logging
import re
import time

try:
    import yfinance as yf
except Exception:
    yf = None

logger = logging.getLogger(__name__)

_NUMERIC_RE = re.compile(r"^\d+$")


def _numeric_exchange_candidates(query: str):
    """2026-07-30 addition ("打0544 滑出全世界0544嘅相關代號"): for a bare
    numeric query, Yahoo's own search index doesn't always resolve a plain
    number to the exchange-suffixed ticker a user actually means -- e.g.
    "0544" needs to become "0544.HK" before Yahoo's lookup recognizes it
    as Daido Group Limited. Mirrors the exact same heuristic js/
    autocomplete.js's normalizeGlobalTicker() already applies client-side
    for the "Analyze" button (HK 4-digit codes, mainland China 6-digit
    Shanghai/Shenzhen codes) so the LIVE search dropdown can surface a
    real match even when the raw numeric query alone doesn't."""
    candidates = []
    if len(query) <= 5:
        candidates.append(query.zfill(4) + ".HK")
    elif len(query) == 6:
        first = query[0]
        if first == "6":
            candidates.append(query + ".SS")
        elif first in ("0", "3"):
            candidates.append(query + ".SZ")
    return candidates

_TYPE_MAP = {
    "EQUITY": "stock",
    "ETF": "etf",
    "CRYPTOCURRENCY": "crypto",
    "INDEX": "index",
    "FUTURE": "futures",
    "CURRENCY": "forex",
    "MUTUALFUND": "etf",
    "OPTION": "stock",
}

# query (lowercased+stripped) -> {"results": [...], "fetched_at": epoch_seconds}
_CACHE: dict = {}
_CACHE_TTL_SECONDS = 600  # 10 min -- long enough to absorb repeat/duplicate
                          # keystrokes across many users for the same
                          # popular query, short enough that a newly-listed
                          # ticker shows up for everyone within minutes
_CACHE_MAX_ENTRIES = 500  # bounded so this never grows into a real memory
                          # leak on the single small Railway dyno this
                          # app runs on -- evicts the oldest entry once full


def _first_present(row, candidates, default=""):
    for c in candidates:
        if c in row and row[c] not in (None, ""):
            return row[c]
    return default


def _cache_get(cache_key: str):
    entry = _CACHE.get(cache_key)
    if not entry:
        return None
    if time.time() - entry["fetched_at"] > _CACHE_TTL_SECONDS:
        del _CACHE[cache_key]
        return None
    return entry["results"]


def _cache_set(cache_key: str, results) -> None:
    if len(_CACHE) >= _CACHE_MAX_ENTRIES:
        oldest_key = min(_CACHE, key=lambda k: _CACHE[k]["fetched_at"])
        del _CACHE[oldest_key]
    _CACHE[cache_key] = {"results": results, "fetched_at": time.time()}


def _lookup_one(candidate: str, limit: int = 1):
    """Run a single yf.Lookup() call and normalize its rows into this
    module's result dict shape. Returns [] on any failure/empty result --
    never raises, so callers can use this for best-effort supplementary
    lookups without their own try/except boilerplate."""
    try:
        lookup = yf.Lookup(candidate, raise_errors=False)
        df = lookup.get_all(count=limit)
        if df is None or df.empty:
            return []
        df = df.reset_index()
        rows = []
        for _, row in df.iterrows():
            row = row.to_dict()
            symbol = _first_present(row, ["symbol", "Symbol", "index"])
            if not symbol:
                continue
            name = _first_present(row, ["shortName", "longName", "name"], symbol)
            quote_type = str(_first_present(row, ["quoteType", "type"], "")).upper()
            exchange = _first_present(row, ["exchange", "exchDisp", "fullExchangeName"])
            rows.append({
                "symbol": symbol,
                "name": name,
                "type": _TYPE_MAP.get(quote_type, "stock"),
                "exchange": exchange,
            })
            if len(rows) >= limit:
                break
        return rows
    except Exception:
        return []


def search_global_assets(query: str, limit: int = 8):
    query = (query or "").strip()
    if not query or yf is None:
        return []

    cache_key = f"{query.lower()}|{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    results = _lookup_one(query, limit=limit)

    # 2026-07-30 addition: a bare numeric query (e.g. "0544") often isn't
    # resolved by Yahoo's own lookup until it's suffixed with the exchange
    # a user actually means (see _numeric_exchange_candidates()'s
    # docstring). Try those candidates too and merge in any real match not
    # already found above, so the dropdown can surface e.g. "0544.HK
    # Daido Group" even when the raw numeric lookup alone came back empty
    # or found something unrelated. Best-effort: never raises, and this
    # whole result (main + candidates) is cached together under the
    # original query so repeat keystrokes don't re-pay this extra call.
    if _NUMERIC_RE.match(query):
        known_symbols = {r["symbol"].upper() for r in results}
        for candidate in _numeric_exchange_candidates(query):
            if candidate.upper() in known_symbols:
                continue
            extra = _lookup_one(candidate, limit=1)
            for r in extra:
                if r["symbol"].upper() not in known_symbols:
                    known_symbols.add(r["symbol"].upper())
                    # Put the exchange-normalized exact match first -- it's
                    # almost always what the user meant by a bare number,
                    # more so than an unrelated fuzzy text match Yahoo's
                    # raw lookup might have returned instead.
                    results.insert(0, r)

    if not results:
        logger.info("ticker_search: zero results (query_len=%d)", len(query))
        _cache_set(cache_key, [])
        return []

    results = results[:limit]
    _cache_set(cache_key, results)
    return results
