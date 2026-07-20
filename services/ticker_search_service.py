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
import time

try:
    import yfinance as yf
except Exception:
    yf = None

logger = logging.getLogger(__name__)

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


def search_global_assets(query: str, limit: int = 8):
    query = (query or "").strip()
    if not query or yf is None:
        return []

    cache_key = f"{query.lower()}|{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        lookup = yf.Lookup(query, raise_errors=False)
        df = lookup.get_all(count=limit)
        if df is None or df.empty:
            logger.info("ticker_search: zero results (query_len=%d)", len(query))
            _cache_set(cache_key, [])
            return []

        df = df.reset_index()
        results = []
        for _, row in df.iterrows():
            row = row.to_dict()
            symbol = _first_present(row, ["symbol", "Symbol", "index"])
            if not symbol:
                continue
            name = _first_present(row, ["shortName", "longName", "name"], symbol)
            quote_type = str(_first_present(row, ["quoteType", "type"], "")).upper()
            exchange = _first_present(row, ["exchange", "exchDisp", "fullExchangeName"])
            results.append({
                "symbol": symbol,
                "name": name,
                "type": _TYPE_MAP.get(quote_type, "stock"),
                "exchange": exchange,
            })
            if len(results) >= limit:
                break
        _cache_set(cache_key, results)
        return results
    except Exception as e:
        # Best-effort supplement -- never let a Yahoo/yfinance hiccup
        # break the autocomplete experience; the local curated list
        # still works either way. Logged (not silently swallowed) so a
        # persistent failure pattern -- e.g. Yahoo throttling this
        # endpoint -- is visible instead of just looking like "no
        # results" forever.
        logger.info("ticker_search: search_global_assets failed (query_len=%d): %s", len(query), e)
        return []
