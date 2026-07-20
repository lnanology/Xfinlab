"""
Fundamentals / Valuation Service (2026-07-18) -- fills the "Valuation:
N/A（暫無估值數據源）" gap flagged in api/ai_analysis.py's dashboard.

Data source: SEC EDGAR's free, official, no-API-key XBRL "companyconcept"
API (see https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
Chosen over the alternatives researched for this:
  - Finnhub's free tier requires written approval for commercial use of
    fundamentals data -- not a clean fit for a commercial product's free
    tier without extra paperwork.
  - Financial Modeling Prep's free tier explicitly requires a separate,
    paid Data Display and Licensing Agreement before displaying or
    redistributing data commercially -- disqualifying on cost grounds
    given this pass's budget constraint, and on compliance grounds
    without that agreement.
  - SEC EDGAR data is public-domain US government data with an
    unambiguous commercial-use precedent (Bloomberg/FactSet/Refinitiv all
    build on the same underlying EDGAR filings) and no rate limit beyond
    a generous 10 requests/second -- genuinely free with zero commercial-
    use ambiguity, the cleanest fit found.

Scope limits, stated honestly (never guessed around):
  - US-listed, SEC-filing companies ONLY (10-K filers). Non-US tickers
    (HK/TW/China/crypto/etc) get an honest "not covered" result, never a
    fabricated number.
  - EPS/Revenue come from the company's own filed XBRL facts (the most
    recent annual 10-K figure) -- filed quarterly/annually, so this is
    NOT a real-time number the way price/volume elsewhere in this
    codebase are. It's combined with the real LIVE price this codebase
    already fetches (services/market_data_service.py) to compute a
    trailing P/E ratio, so the P/E itself does track today's price even
    though the EPS denominator only updates once a quarter/year.
  - Different companies tag the same accounting concept under different
    XBRL tags (EarningsPerShareDiluted vs EarningsPerShareBasic,
    Revenues vs RevenueFromContractWithCustomerExcludingAssessedTax) --
    this tries a short list of common tags per concept and uses whichever
    has data, rather than guessing a company-specific mapping that could
    silently be wrong.
"""

import logging
from datetime import date
from typing import Dict, List, Optional

from services.outbound_http import get_with_backoff

logger = logging.getLogger(__name__)

# SEC explicitly requires an identifying User-Agent with contact info on
# every request (see their API docs) -- reusing the same honest-UA
# convention as services/outbound_http.py's default, just SEC-specific
# per their stated preference for a per-integration contact string.
SEC_USER_AGENT = "XFINLABBot/1.0 (+https://www.xfinlab.com; contact: support@xfinlab.com)"

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json"

EPS_TAGS = ["EarningsPerShareDiluted", "EarningsPerShareBasic"]
REVENUE_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]
# 2026-07-20 addition (task #289, "加入如morningstar, 公司純利及收入"): net
# income, same free SEC EDGAR source as EPS/Revenue above -- NetIncomeLoss
# is the standard us-gaap tag virtually all 10-K filers use for this line.
NET_INCOME_TAGS = ["NetIncomeLoss"]

_CACHE_TTL_DAYS = 7  # ticker->CIK mapping barely changes day to day
_ticker_cik_cache = {"data": None, "fetched_at": None}
_fundamentals_cache: Dict[str, Dict] = {}  # symbol -> {"date": iso, "data": {...}}


def _load_ticker_cik_map() -> dict:
    today = date.today()
    cached = _ticker_cik_cache["data"]
    fetched_at = _ticker_cik_cache["fetched_at"]
    if cached and fetched_at and (today - fetched_at).days < _CACHE_TTL_DAYS:
        return cached
    try:
        res = get_with_backoff(TICKER_MAP_URL, headers={"User-Agent": SEC_USER_AGENT}, timeout=20)
        if res.status_code != 200:
            return cached or {}
        payload = res.json()
        mapping = {str(entry["ticker"]).upper(): entry["cik_str"] for entry in payload.values()}
        _ticker_cik_cache["data"] = mapping
        _ticker_cik_cache["fetched_at"] = today
        return mapping
    except Exception as e:
        logger.info("fundamentals_service: ticker->CIK map fetch failed: %s", e)
        return cached or {}


def _fetch_concept_series(cik: int, tags: List[str]) -> Optional[List[Dict]]:
    """
    Same annual-10-K-only filtering as _fetch_concept() below, but returns
    the FULL sorted annual series instead of just the latest point --
    needed for Stage-1 Smart Beta's Quality/Growth factor (2026-07-19),
    which needs a real YoY comparison, not just the newest figure.
    """
    for tag in tags:
        try:
            url = CONCEPT_URL.format(cik=cik, tag=tag)
            res = get_with_backoff(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=20)
            if res.status_code != 200:
                continue
            payload = res.json()
            units = payload.get("units", {})
            series = units.get("USD/shares") or units.get("USD")
            if not series:
                continue
            annual = [p for p in series if p.get("form") == "10-K" and p.get("fp") == "FY" and p.get("val") is not None]
            if not annual:
                continue
            annual.sort(key=lambda p: p.get("end", ""))
            return annual
        except Exception as e:
            logger.info("fundamentals_service: concept series fetch failed for tag %s: %s", tag, e)
            continue
    return None


def _fetch_concept(cik: int, tags: List[str]) -> Optional[Dict]:
    annual = _fetch_concept_series(cik, tags)
    if not annual:
        return None
    latest = annual[-1]
    return {"value": latest["val"], "fiscal_year": latest.get("fy"), "period_end": latest.get("end")}


def get_fundamentals(symbol: str, current_price: Optional[float] = None) -> Dict:
    """
    Returns:
        {"status": "ok", "available": True, "source": "SEC EDGAR (官方申報數據)",
         "eps": {...}|None, "revenue": {...}|None, "pe_ratio": float|None, "note": "..."}
        {"status": "ok", "available": False, "message": "..."}  -- non-US
            ticker or no SEC data found, never a fabricated number
    """
    bare_symbol = (symbol or "").strip().upper().split(".")[0]
    if not bare_symbol:
        return {"status": "error", "available": False, "message": "代號格式無效"}

    today = date.today().isoformat()
    cached = _fundamentals_cache.get(bare_symbol)
    if cached and cached["date"] == today:
        result = dict(cached["data"])
        eps = result.get("eps")
        if result.get("available") and current_price and eps and eps.get("value"):
            result["pe_ratio"] = round(current_price / eps["value"], 2) if eps["value"] > 0 else None
        return result

    cik_map = _load_ticker_cik_map()
    if not cik_map:
        # Couldn't reach SEC at all -- an honest "couldn't verify" message,
        # not the same claim as "confirmed this isn't a US SEC filer".
        return {"status": "ok", "available": False, "message": "暫時無法連接SEC EDGAR，請稍後重試。"}

    cik = cik_map.get(bare_symbol)
    if not cik:
        result = {"status": "ok", "available": False, "message": f"{bare_symbol} 唔係美股SEC申報公司，暫無估值數據。"}
        _fundamentals_cache[bare_symbol] = {"date": today, "data": result}
        return result

    eps = _fetch_concept(cik, EPS_TAGS)
    revenue_series = _fetch_concept_series(cik, REVENUE_TAGS)
    revenue = {"value": revenue_series[-1]["val"], "fiscal_year": revenue_series[-1].get("fy"),
               "period_end": revenue_series[-1].get("end")} if revenue_series else None
    net_income = _fetch_concept(cik, NET_INCOME_TAGS)

    # 2026-07-19 Stage-1 Smart Beta addition: real YoY revenue growth as
    # the Quality/Growth factor input (see services/smart_beta_service.py)
    # -- reuses the SAME annual series already being fetched for the
    # "revenue" field above rather than making a second SEC request.
    # Needs at least 2 annual points; honestly omitted (never estimated)
    # if the company only has 1 year of 10-K history on file.
    revenue_growth_pct = None
    if revenue_series and len(revenue_series) >= 2:
        prev_val = revenue_series[-2]["val"]
        latest_val = revenue_series[-1]["val"]
        if prev_val:
            revenue_growth_pct = round((latest_val - prev_val) / abs(prev_val) * 100, 1)

    if not eps and not revenue and not net_income:
        result = {"status": "ok", "available": False, "message": f"暫時攞唔到 {bare_symbol} 嘅SEC申報數據。"}
        _fundamentals_cache[bare_symbol] = {"date": today, "data": result}
        return result

    result = {
        "status": "ok",
        "available": True,
        "source": "SEC EDGAR (官方申報數據)",
        "eps": eps,
        "revenue": revenue,
        "revenue_growth_pct": revenue_growth_pct,
        "net_income": net_income,
        "pe_ratio": None,
        "note": "EPS／營收／純利數字嚟自最近一份10-K年報申報，並非即時數據；市盈率(P/E)由即時股價與最近年度EPS計算得出。",
    }
    if current_price and eps and eps.get("value") and eps["value"] > 0:
        result["pe_ratio"] = round(current_price / eps["value"], 2)

    _fundamentals_cache[bare_symbol] = {"date": today, "data": result}
    return result
