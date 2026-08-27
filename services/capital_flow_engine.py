"""2026-08-24 (AJ: "以資金流建預測不同資產K線走向ENGINE，包括突發事件，政策，討論" --
build an Engine that uses capital flow to predict K-line direction across
asset classes; later: "唔使錢同我全拉入來，建全球化" -- pull in every $0
global data source, build the globalization angle).

Scope decision made with AJ before writing this file: the full 7-layer /
15-section design he was pitched externally (Capital Flow -> Liquidity ->
Regime -> Event Shock -> Cross-Asset -> Probabilistic K-Line, plus Options
Flow / Dark Pool / COT / on-chain whale tracking) is a multi-year
institutional build. Real options-flow/dark-pool/COT/institutional-flow
data requires paid vendors (Unusual Whales, Quiver Quant, EPFR) this
codebase does not have and this file does NOT fabricate any of it.

What this file actually is: an honest, $0-data "Capital Flow Score" --
Phase 1 of that roadmap, reusing infrastructure already live in this
codebase rather than duplicating it:
  - Cross-region rotation: reuses services/technical_analysis_service.py's
    already-audited Confluence Engine over a basket of REGIONAL index ETFs
    (not just US) -- this is the "globalization" half of AJ's instruction.
    A researched attempt to pull real HKEX Northbound/Southbound Stock
    Connect flow (genuinely free, official, and would have been a much
    stronger signal than an ETF proxy) was investigated and abandoned for
    now: HKEX's historical-daily page is JS-rendered with no discovered
    stable CSV/JSON endpoint, and the one open-source scraper that used to
    cover it (AKShare's HSGT functions) has been broken since the SSE/SZSE
    disclosure change on 2024-08-19. Revisit if a reliable source turns up
    -- do not silently reintroduce a fragile scrape here.
  - Sector rotation: same Confluence Engine over the full 11 SPDR sector
    ETFs (upgrades api/market_pulse.py's existing 3-sector "fund_flow"
    label, which -- worth flagging honestly -- is currently just a relabel
    of its 8-ticker sentiment basket, not a real flow measurement either).
  - Liquidity: services/fred_macro_service.py's new get_liquidity_snapshot()
    (M2 / Fed balance sheet / reverse repo) -- genuine upstream liquidity
    data, US-only (FRED has no equivalent free global series).
  - Fiscal liquidity (2026-08-27 addition): services/treasury_fiscal_
    service.py's Treasury General Account balance trend -- the fiscal-side
    counterpart to the Fed-side liquidity above (see _compute_snapshot's
    comment for the tailwind/headwind rationale). Also US-only.
  - Volume-based per-symbol flow: formula_engine.money_flow_index(), which
    existed but was never wired into anything -- OBV already is (see
    technical_analysis_service.py's obv_trend, Confluence signal #7).

Every score this module returns is labeled "model_derived" -- computed
from public price/volume/macro data, NOT real institutional order flow,
options positioning, or fund creation/redemption data. That distinction
gets surfaced in every response so nothing downstream (UI copy, API docs,
sales copy) can accidentally overclaim it as real flow data.
"""
import time
from typing import Dict, List, Optional

# Regional index/country ETFs -- deliberately proxies (relative price
# momentum via the Confluence Engine), not real cross-border capital flow
# data (no free source found, see module docstring). Picked for liquid,
# well-known single-ETF coverage per region rather than exhaustive.
_GLOBAL_REGION_BASKET = {
    "US": "SPY",
    "Europe": "VGK",
    "Japan": "EWJ",
    "Greater China": "FXI",
    "Hong Kong": "EWH",
    "Emerging Markets": "EEM",
    "India": "INDA",
}

# Full 11 SPDR Select Sector ETFs -- upgrade from api/market_pulse.py's
# 3-sector (XLK/XLF/XLE) subset used for its "fund_flow" homepage label.
_SECTOR_BASKET = {
    "Technology": "XLK", "Financials": "XLF", "Energy": "XLE",
    "Healthcare": "XLV", "Consumer Discretionary": "XLY", "Consumer Staples": "XLP",
    "Industrials": "XLI", "Utilities": "XLU", "Materials": "XLB",
    "Real Estate": "XLRE", "Communication Services": "XLC",
}

_CACHE_TTL_SECONDS = 1800  # 30min -- heavier multi-ticker scan than market_pulse's 5min
_cache: Optional[Dict] = None
_cache_time: float = 0.0

# Reentrancy guard -- _compute_snapshot() below calls get_technical_analysis()
# for every basket ticker (SPY, XLK, ...), and get_technical_analysis()
# itself calls back into get_capital_flow_signal_for_confluence() (see
# technical_analysis_service.py's 2026-08-24 addition) to add THIS engine's
# reading as one of its own Confluence votes. Without this flag, computing
# the snapshot for the very first basket ticker would trigger another full
# snapshot computation, which triggers another for ITS first ticker, and so
# on -- unbounded recursion / stack overflow. While a snapshot computation
# is already in flight, the Confluence Engine just doesn't get a
# capital_flow vote for that call (same "signal not available" honesty as
# every other optional signal) rather than deadlocking or crashing.
_computing = False


def _rank_basket(basket: Dict[str, str]) -> Optional[Dict]:
    """Runs the existing Confluence Engine over every ticker in `basket`
    (name -> ticker), returns a ranked list + net average score. Lazy
    import to avoid a circular import (technical_analysis_service.py
    calls back into this module for the per-symbol capital_flow signal --
    see get_capital_flow_signal_for_confluence below)."""
    from services.technical_analysis_service import get_technical_analysis

    ranked: List[Dict] = []
    for name, ticker in basket.items():
        try:
            tech = get_technical_analysis(ticker, period="3mo")
        except Exception:
            tech = None
        if not tech or "error" in tech:
            continue
        confluence = tech.get("confluence", {})
        ranked.append({
            "name": name,
            "ticker": ticker,
            "score": confluence.get("score", 0.0),
            "direction": confluence.get("direction"),
        })

    if not ranked:
        return None
    ranked.sort(key=lambda r: r["score"], reverse=True)
    avg_score = round(sum(r["score"] for r in ranked) / len(ranked), 1)
    return {
        "ranked": ranked,
        "avg_score": avg_score,
        "inflow_leader": ranked[0],
        "outflow_leader": ranked[-1] if len(ranked) > 1 else None,
    }


def _compute_snapshot() -> Dict:
    region = _rank_basket(_GLOBAL_REGION_BASKET)
    sector = _rank_basket(_SECTOR_BASKET)

    try:
        from services.fred_macro_service import get_liquidity_snapshot
        liquidity = get_liquidity_snapshot()
    except Exception:
        liquidity = {"available": False, "message": "流動性數據暫時無法計算。"}

    # 2026-08-27 (Data Factory Step 8 follow-up, AJ: "加落Capital Flow
    # Engine"): the FISCAL side of liquidity, complementing FRED's Fed-
    # side series above. The Treasury General Account (TGA) is the
    # federal government's own checking account at the Fed -- when its
    # balance FALLS, the Treasury is spending accumulated cash back into
    # the economy (a genuine liquidity tailwind, independent of anything
    # the Fed itself is doing); when it RISES (e.g. after a big debt
    # issuance settles), cash is being pulled OUT of the economy into
    # that account (a headwind). Same directional-scaled-to-±100
    # convention as fred_macro_service.get_liquidity_snapshot's reverse-
    # repo inversion, not a statistical z-score. Total public debt
    # outstanding is surfaced for context but deliberately NOT scored --
    # debt level alone doesn't have a clean, uncontested short-term
    # direction for market liquidity the way a cash-balance draw/build
    # does, and this module's honesty rule is to only score what has an
    # unambiguous sign.
    try:
        from services.treasury_fiscal_service import get_snapshot as get_treasury_snapshot
        fiscal = get_treasury_snapshot()
    except Exception:
        fiscal = {"available": False, "message": "財政部數據暫時無法計算。"}

    fiscal_score = None
    if fiscal.get("available"):
        tga = fiscal.get("series", {}).get("treasury_general_account_balance_usd_millions")
        if tga and tga.get("period_change_pct") is not None:
            # Falling TGA (negative period_change_pct) -> tailwind -> positive score.
            # x10 scale + clamp to ±100: a ~10%/month TGA swing (a large
            # but not unprecedented move) maps to a full-strength reading,
            # matching the FRED liquidity score's own scale.
            fiscal_score = max(-100.0, min(100.0, round(-tga["period_change_pct"] * 10, 1)))

    # Composite: simple average of whichever components are actually
    # available (region rotation, sector rotation, US Fed-side liquidity,
    # US fiscal-side liquidity) -- never fabricates a missing component,
    # matches every other honesty convention in this codebase (FRED's
    # "." handling, dormant-until-configured Stripe/addon services, etc.).
    components = []
    if region:
        components.append(region["avg_score"])
    if sector:
        components.append(sector["avg_score"])
    if liquidity.get("available"):
        components.append(liquidity["liquidity_score"])
    if fiscal_score is not None:
        components.append(fiscal_score)

    composite = round(sum(components) / len(components), 1) if components else None
    if composite is None:
        direction = "數據不足"
    elif composite >= 20:
        direction = "資金淨流入（風險偏好上升）"
    elif composite <= -20:
        direction = "資金淨流出（風險偏好下降）"
    else:
        direction = "資金流向分歧，中性"

    return {
        "as_of": time.time(),
        "capital_flow_score": composite,
        "capital_flow_direction": direction,
        "estimate_basis": "model_derived",
        "disclaimer": "此分數由公開價格/成交量/宏觀數據推算，並非真實機構資金流、期權流或暗池數據 -- 詳見 estimate_basis。",
        "region_rotation": region,
        "sector_rotation": sector,
        "liquidity": liquidity,
        "fiscal": {**fiscal, "fiscal_score": fiscal_score} if fiscal.get("available") else fiscal,
    }


def get_capital_flow_snapshot(force_refresh: bool = False) -> Dict:
    """Public entrypoint for a FULL (possibly slow -- ~18 tickers + 1 FRED
    call) computation. This is ONLY ever called by refresh_capital_flow_
    cache() below (the scheduled cron job in backend/main.py) or an admin
    manual-trigger. It must NEVER be called from inside a live user
    request (get_technical_analysis()/Confluence Engine reads the cache
    directly via get_capital_flow_signal_for_confluence() instead) -- an
    earlier version of this file did call this inline on cache-miss, which
    meant the first chart-search/ai-analysis request after every 30min
    cache expiry silently paid for an 18-ticker sequential scan on top of
    its own single-ticker fetch. Confirmed in production: a live
    /chart-search/AAPL request timed out (>180s) the first time this ran.
    Fixed by fully decoupling computation (cron-only, this function) from
    reads (cache-only, get_capital_flow_signal_for_confluence)."""
    global _cache, _cache_time, _computing
    now = time.time()
    if not force_refresh and _cache is not None and (now - _cache_time) < _CACHE_TTL_SECONDS:
        return {**_cache, "cached": True}
    if _computing:
        # Reentrant call -- shouldn't happen now that the Confluence Engine
        # only ever reads the cache (see get_capital_flow_signal_for_
        # confluence), but kept as a defensive guard in case another
        # caller is added later that isn't as careful.
        return {**_cache, "cached": True} if _cache else {"capital_flow_score": None, "cached": True}
    _computing = True
    try:
        result = _compute_snapshot()
    finally:
        _computing = False
    _cache = result
    _cache_time = now
    return {**result, "cached": False}


def refresh_capital_flow_cache():
    """Scheduled-job entry point (backend/main.py, cron) -- the ONLY
    routine call path that ever triggers the full 18-ticker + FRED scan.
    Runs off the user request path entirely, same convention as market_
    pulse.py's refresh_free_signals_and_notify()."""
    get_capital_flow_snapshot(force_refresh=True)


def get_capital_flow_signal_for_confluence() -> Optional[Dict]:
    """Read-only, in-memory cache peek for technical_analysis_service.py's
    Confluence Engine -- NEVER triggers a computation, NEVER makes a
    network call, so adding this signal to every single chart/analysis
    request costs nothing beyond a dict lookup. Returns None (signal not
    counted, same as every other optional Confluence input) until the
    scheduled job above has populated the cache at least once -- e.g. for
    a few minutes right after a fresh deploy."""
    if _cache is None or _cache.get("capital_flow_score") is None:
        return None
    return {"score": _cache["capital_flow_score"], "direction": _cache["capital_flow_direction"]}


if __name__ == "__main__":
    import json
    print(json.dumps(get_capital_flow_snapshot(), indent=2, ensure_ascii=False, default=str))
