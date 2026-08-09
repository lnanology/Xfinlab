"""
2026-08-10 (task #747-751, AJ: "所有卡片有資產的都加細K線小圖" -- 全站所有
頁). Generic per-ticker sparkline lookup, for pages whose primary data
endpoint doesn't return a ticker-keyed structured list (so there's no
single natural spot to embed a "sparkline" field server-side) -- e.g.
screener.html's results come back as free-form AI-generated markdown text
(api/ai_analysis.py), and company_compare.py / watchlist.py build their
responses from services/market_data_service.py's `.info`-only snapshot
with no OHLC history fetched anywhere in that path.

Rather than reshape those endpoints' response contracts (real risk of
regressing pages already relying on their exact current shape), the
frontend on those pages fetches this small endpoint once per ticker it
already knows about (after its own primary render), same pattern as
autocomplete.js's live-search calls. See js/sparkline.js's usage comment
for the client side of this.

Pages that already had OHLC history in-hand from their own primary call
(chat.html's on-demand asset card via api/ai_analysis.py's `ohlc` field,
services/anomaly_history_service.py's 30-day scan) don't use this at all
-- they slice their own already-fetched data instead, for zero extra
requests.
"""

import re

from fastapi import APIRouter

from services.sparkline_service import get_recent_closes

router = APIRouter()

# Same ticker-format guard used by api/anomaly.py / api/chart_analysis.py.
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-=^]{1,12}$")


@router.get("/sparkline/{ticker}")
def sparkline(ticker: str):
    """Last ~20 daily closes for one ticker, ready for
    XflSparkline.render() on the frontend. Always returns 200 with an
    empty list on any failure (bad ticker, data source down) -- callers
    treat an empty/missing sparkline as "just don't draw one for this
    card", never as an error to surface to the user.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker or not _SYMBOL_RE.match(ticker):
        return {"ticker": ticker, "sparkline": []}
    return {"ticker": ticker, "sparkline": get_recent_closes(ticker)}
