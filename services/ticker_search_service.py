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
"""
try:
    import yfinance as yf
except Exception:
    yf = None

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


def _first_present(row, candidates, default=""):
    for c in candidates:
        if c in row and row[c] not in (None, ""):
            return row[c]
    return default


def search_global_assets(query: str, limit: int = 8):
    query = (query or "").strip()
    if not query or yf is None:
        return []

    try:
        lookup = yf.Lookup(query, raise_errors=False)
        df = lookup.get_all(count=limit)
        if df is None or df.empty:
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
        return results
    except Exception:
        # Best-effort supplement -- never let a Yahoo/yfinance hiccup
        # break the autocomplete experience; the local curated list
        # still works either way.
        return []
