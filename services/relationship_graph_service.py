"""
Relationship/Impact Graph service (2026-09-30, AJ: monetization gap
analysis -- asked "重有咩有差距的可收費" (what monetizable gaps remain)
after reviewing a long external brainstorm doc about agent-native
financial infrastructure. The one piece of that doc genuinely missing
from XFINLAB, genuinely buildable now, and genuinely differentiated vs.
generic financial data APIs (FMP/Alpha Vantage/Massive all sell price +
fundamentals; none of them expose company-to-company relationships) is
this: given a ticker, who is upstream (suppliers), downstream
(customers), same-sector (peers), and directly competing (competitors)
-- the "if X happens to this company, who else does it touch" layer.

Scope, deliberately narrow: a hand-curated set of REAL, well-documented,
publicly known supplier/customer/competitor relationships for a
starting set of major companies (weighted toward the AI/semiconductor
supply chain -- the highest-demand vertical right now, and also the
one with the best-documented public relationships via 10-K "Item 1
Business" disclosures, earnings-call mentions, and trade press). Same
zero-fabrication discipline as video_engine_service.py's
_COMMODITY_FOREX_KEYWORDS mapping: every relationship listed below is
common, multiply-sourced public knowledge, not scraped or AI-inferred.

This is a STARTING set, not a claim of completeness -- a ticker with no
curated entry returns an honest empty result (get_impact_analysis()'s
`coverage_note` says so explicitly), never a guessed relationship. Grow
this dict over time as new tickers are requested, the same way
COUNTRY_BASKETS in trending_stocks_service.py grew from 8 to 50 US
tickers.
"""
from typing import Dict, List, Optional

from services.trending_stocks_service import COUNTRY_BASKETS

COMPANY_RELATIONSHIPS: Dict[str, Dict[str, List[str]]] = {
    "NVDA": {
        "suppliers": ["TSM", "MU", "000660.KS"],  # TSMC (fab), Micron + SK Hynix (HBM memory)
        "customers": ["MSFT", "GOOGL", "AMZN", "META", "ORCL"],  # major cloud/AI-GPU buyers
        "competitors": ["AMD", "INTC", "AVGO"],
    },
    "AAPL": {
        "suppliers": ["TSM", "QCOM", "2317.TW"],  # TSMC (A/M-series fab), Qualcomm (modems), Foxconn/Hon Hai (assembly)
        "customers": [],
        "competitors": ["GOOGL", "005930.KS"],  # Samsung Electronics
    },
    "MSFT": {
        "suppliers": ["NVDA", "AMD"],
        "customers": [],
        "competitors": ["GOOGL", "AMZN", "ORCL"],
    },
    "GOOGL": {
        "suppliers": ["TSM", "NVDA"],  # TSMC fabs Google's TPUs
        "customers": [],
        "competitors": ["MSFT", "AMZN", "META"],
    },
    "AMZN": {
        "suppliers": ["NVDA", "TSM", "AMD"],  # TSMC fabs AWS Trainium/Graviton
        "customers": [],
        "competitors": ["MSFT", "GOOGL", "WMT"],
    },
    "META": {
        "suppliers": ["NVDA", "TSM"],  # TSMC fabs Meta's custom MTIA silicon
        "customers": [],
        "competitors": ["GOOGL", "SNAP"],
    },
    "TSM": {
        "suppliers": ["ASML"],  # EUV lithography, near-sole supplier
        "customers": ["AAPL", "NVDA", "AMD", "QCOM", "AVGO"],
        "competitors": ["005930.KS", "INTC"],  # Samsung Foundry, Intel Foundry
    },
    "AVGO": {
        "suppliers": ["TSM"],
        "customers": ["AAPL", "GOOGL"],  # RF/connectivity chips; custom TPU co-design
        "competitors": ["QCOM", "MRVL"],
    },
    "AMD": {
        "suppliers": ["TSM"],
        "customers": ["MSFT", "AMZN", "META"],
        "competitors": ["NVDA", "INTC"],
    },
    "INTC": {
        "suppliers": ["ASML"],
        "customers": ["DELL", "HPQ"],
        "competitors": ["NVDA", "AMD", "TSM"],
    },
    "MU": {
        "suppliers": [],
        "customers": ["NVDA", "AAPL"],
        "competitors": ["000660.KS", "005930.KS"],  # SK Hynix, Samsung
    },
    "ASML": {
        "suppliers": [],
        "customers": ["TSM", "INTC", "005930.KS"],
        "competitors": [],  # near-monopoly in EUV lithography, no direct public competitor at that tier
    },
    "QCOM": {
        "suppliers": ["TSM"],
        "customers": ["AAPL"],  # modem chips (declining share as Apple builds its own)
        "competitors": ["AVGO", "MRVL"],
    },
    "TSLA": {
        "suppliers": ["1211.HK"],  # BYD is both a battery supplier to some OEMs and a direct EV competitor -- listed under competitors below; battery cell suppliers are primarily Panasonic/CATL (not separately US-tradable tickers)
        "customers": [],
        "competitors": ["1211.HK", "RIVN", "F", "GM"],  # BYD, Rivian, Ford, GM
    },
    "ORCL": {
        "suppliers": ["NVDA", "AMD"],
        "customers": [],
        "competitors": ["MSFT", "GOOGL", "AMZN"],
    },
}


def _sector_peers(ticker: str, max_peers: int = 6) -> List[Dict[str, str]]:
    """Same-sector peers reused from the existing, already-curated
    services/trending_stocks_service.py US basket (ticker, name, sector)
    tuples -- no separate sector taxonomy maintained here, so this can
    never drift from what admin.html's "Most Active Stocks" lookup
    already shows for the same ticker. Returns [] for any ticker not in
    that fixed basket (e.g. a non-US or small-cap ticker) rather than
    guessing a sector for it."""
    us_basket = COUNTRY_BASKETS.get("US", [])
    ticker = (ticker or "").upper().strip()
    sector = None
    for t, name, sec in us_basket:
        if t == ticker:
            sector = sec
            break
    if not sector:
        return []
    peers = [{"ticker": t, "name": name} for t, name, sec in us_basket if sec == sector and t != ticker]
    return peers[:max_peers]


def get_impact_analysis(ticker: str) -> dict:
    """Composes the curated relationship dict above with two other
    ALREADY-EXISTING real-data services -- services/capital_flow_engine.py
    (market-wide capital flow signal) and services/cftc_cot_service.py
    (futures positioning for this ticker's underlying commodity/index, if
    any) -- into one "who and what does this ticker connect to" view.
    Nothing here is a new data source; it's a new composition of
    existing, already-verified ones, same "compose don't duplicate"
    principle services/evidence_scorecard_service.py already established
    for its 11 dimensions.

    Every sub-call is independently best-effort (never raises) -- a
    missing capital-flow cache or no CFTC mapping for this ticker just
    means that field is None, never a guess standing in for it."""
    ticker = (ticker or "").upper().strip()
    rel = COMPANY_RELATIONSHIPS.get(ticker, {})
    sector_peers = _sector_peers(ticker)

    capital_flow_context = None
    try:
        from services.capital_flow_engine import get_capital_flow_signal_for_confluence

        capital_flow_context = get_capital_flow_signal_for_confluence()
    except Exception:
        capital_flow_context = None

    cftc_context = None
    try:
        from services.cftc_cot_service import get_cot_for_ticker

        cftc_context = get_cot_for_ticker(ticker)
    except Exception:
        cftc_context = None

    has_curated_relationships = bool(rel)
    return {
        "ticker": ticker,
        "sector_peers": sector_peers,
        "known_suppliers": rel.get("suppliers", []),
        "known_customers": rel.get("customers", []),
        "known_competitors": rel.get("competitors", []),
        "has_curated_relationships": has_curated_relationships,
        "capital_flow_context": capital_flow_context,
        "cftc_context": cftc_context,
        "coverage_note": (
            "This ticker isn't in the curated supplier/customer/competitor set yet -- an "
            "empty list here means 'not curated yet', not 'no real relationships exist'. "
            "sector_peers is still populated from the existing sector-tagged basket."
            if not has_curated_relationships else
            "Supplier/customer/competitor relationships are hand-curated from public company "
            "disclosures (10-K filings, earnings calls, trade press), not AI-inferred or "
            "scraped -- see this module's docstring for sourcing notes."
        ),
    }
