"""
Opportunity Radar -- 2026-08-31, first build under the "Xfinlab extension"
path (AJ chose this over a standalone new product, see chat -- reuse
existing Data Factory data to answer "where's a structural macro
mismatch developing", not "should I buy this stock").

What this is NOT: a fabricated single "Opportunity Score" that pretends
to combine mortgage rates, manufacturing orders, and retail sales into
one comparable 0-100 number. There is no principled way to weight those
against each other -- any such score would just be made-up coefficients
dressed up as an algorithm, which violates this codebase's zero-
fabrication standard as much as a fake headline would.

What this IS: for each already-built industry vertical (real estate,
supply chain, consumer demand -- see services/real_estate_service.py,
services/supply_chain_service.py, services/consumer_demand_service.py)
plus a US macro backdrop (services/fred_macro_service.py), pull each
indicator's own recent observation history (these modules' _fetch_series
already supports n_obs>1, no new fetch logic needed) and report the
real, literal percentage change between the latest observation and the
oldest one in that trailing window -- plus a plain count of "how many of
this industry's indicators moved improving vs worsening", never a
synthesized score. The reader draws their own conclusion from real
numbers; this module's only editorializing is the up/down/flat label,
which is a mechanical threshold on a computed %, not an opinion.

Scope, stated honestly: only the 3 industries with a FRED-style
_fetch_series(series_id, n_obs) signature are covered today. EIA
(energy) and USDA (agriculture) use a different fetch shape (route-
based, not a flat series_id) and would need dedicated adaptation --
deliberately not rushed in here; a wrong quick port is worse than an
honestly-scoped gap. Add them as a follow-up, not by silently forcing
them into this module's shape.

Zero new API integration, zero new signup: reuses the same FRED-backed
modules already live and gated behind FRED_API_KEY. This module itself
fetches nothing new from FRED directly -- it only re-calls each
existing module's own _fetch_series(), inheriting that module's cache/
persistence/fallback chain, same "zero new data source" convention as
Company Network Phase 4's crossholdings re-query.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# How many trailing observations to compare latest-vs-oldest across. Not
# a fixed calendar window -- source series have different frequencies
# (weekly mortgage rate vs monthly housing starts vs daily yield curve),
# so each indicator's actual date range is reported explicitly
# (compare_date/latest_date) rather than implying a uniform "6 months"
# that isn't true for every series.
_TRAILING_OBS = 6

# % change threshold below which a move is called "flat" rather than
# up/down -- avoids labelling normal noise as a "trend". Chosen as a
# round, conservative number, not fit to any backtest.
_FLAT_THRESHOLD_PCT = 0.5


def _trend_for_series(fetch_fn, series_id: str, label: str, unit: str,
                       higher_is_improving: bool) -> Optional[Dict]:
    """Fetches _TRAILING_OBS observations via the given module's own
    _fetch_series(series_id, n_obs) and returns a real, computed % change
    between the oldest and latest point in that window -- None if fewer
    than 2 usable observations exist (never fabricates a change from a
    single point).

    `higher_is_improving`: whether a rising reading is the "improving"
    direction for this specific indicator (e.g. housing starts rising is
    improving; mortgage rate rising is NOT -- lower financing cost is the
    improving direction there). This is a factual property of the
    indicator's real-world meaning, documented per-series at the call
    site below, not a subjective weighting.
    """
    try:
        obs = fetch_fn(series_id, n_obs=_TRAILING_OBS)
    except Exception as e:
        logger.info("opportunity_radar_service: fetch failed for %s: %s", series_id, e)
        return None
    if not obs or len(obs) < 2:
        return None

    oldest, latest = obs[0], obs[-1]
    if not oldest.get("value"):
        return None
    pct_change = round((latest["value"] - oldest["value"]) / abs(oldest["value"]) * 100, 2)

    if abs(pct_change) < _FLAT_THRESHOLD_PCT:
        direction = "flat"
        improving = None
    else:
        direction = "up" if pct_change > 0 else "down"
        rising_is_improving = higher_is_improving
        improving = (direction == "up") == rising_is_improving

    return {
        "label": label,
        "unit": unit,
        "latest_date": latest["date"],
        "latest_value": latest["value"],
        "compare_date": oldest["date"],
        "compare_value": oldest["value"],
        "pct_change": pct_change,
        "direction": direction,
        "improving": improving,  # True/False/None(flat) -- factual given higher_is_improving, not a score
    }


def _industry_summary(indicators: List[Optional[Dict]]) -> Dict:
    usable = [i for i in indicators if i is not None]
    improving = sum(1 for i in usable if i.get("improving") is True)
    worsening = sum(1 for i in usable if i.get("improving") is False)
    flat = sum(1 for i in usable if i.get("direction") == "flat")
    return {
        "indicators_available": len(usable),
        "improving_count": improving,
        "worsening_count": worsening,
        "flat_count": flat,
        "summary": (
            f"{improving} of {len(usable)} tracked indicators improving, "
            f"{worsening} worsening, {flat} flat"
            if usable else "No indicators currently available"
        ),
    }


def get_opportunity_radar() -> Dict:
    """Returns:
        {"available": True, "as_of": "...", "attribution": "...",
         "macro_backdrop": {"indicators": {...}, ...summary fields},
         "industries": {
            "real_estate": {"label": "Real Estate", "indicators": {...}, ...summary},
            "supply_chain": {...},
            "consumer_demand": {...},
         },
         "methodology_note": "..."}
        or {"available": False, "message": "..."} if FRED_API_KEY isn't
        set (checked via real_estate_service.is_available(), since all
        4 underlying modules share the same FRED_API_KEY gate).
    """
    from services import real_estate_service, supply_chain_service, consumer_demand_service, fred_macro_service

    if not real_estate_service.is_available():
        return {"available": False, "message": "FRED_API_KEY 未設定，Opportunity Radar 暫時未開放。"}

    # Macro backdrop -- higher_is_improving is deliberately omitted here
    # (left as direction only, no improving/worsening label) because
    # "is rising unemployment bad" etc. depends on where in the cycle you
    # are -- unlike the industry indicators below, these don't have a
    # single always-true improving direction, so labelling one would be
    # editorializing, not reporting. Direction (up/down/flat) is still a
    # plain fact.
    macro_specs = [
        ("fed_funds_rate_pct", "FEDFUNDS", "Federal Funds Rate", "%"),
        ("unemployment_pct", "UNRATE", "Unemployment Rate", "%"),
        ("yield_curve_10y2y_pct", "T10Y2Y", "10Y-2Y Treasury Yield Spread", "%"),
        ("jobless_claims_initial", "ICSA", "Initial Jobless Claims", "claims"),
    ]
    macro_indicators = {}
    for key, series_id, label, unit in macro_specs:
        t = _trend_for_series(fred_macro_service._fetch_series, series_id, label, unit, higher_is_improving=True)
        if t:
            t.pop("improving", None)  # direction-only for macro, see note above
        macro_indicators[key] = t

    # Industry verticals -- higher_is_improving is a factual property of
    # each series (documented inline), not a subjective call.
    industry_specs = {
        "real_estate": {
            "module": real_estate_service,
            "label": "Real Estate",
            "series": [
                ("mortgage_rate_30y_pct", False),   # lower financing cost = improving for the sector
                ("home_price_index", True),
                ("housing_starts_thousands", True),
                ("existing_home_sales_thousands", True),
            ],
        },
        "supply_chain": {
            "module": supply_chain_service,
            "label": "Supply Chain / Manufacturing",
            "series": [
                ("inventory_sales_ratio", False),   # falling ratio = tighter availability/restocking demand
                ("manufacturing_new_orders_musd", True),
                ("durable_goods_orders_musd", True),
                ("industrial_production_manufacturing_index", True),
                ("manufacturing_employment_thousands", True),
            ],
        },
        "consumer_demand": {
            "module": consumer_demand_service,
            "label": "Consumer Demand / Retail",
            "series": [
                ("retail_sales_total_musd", True),
                ("retail_sales_goods_only_musd", True),
                ("personal_consumption_expenditures_busd", True),
                ("durable_goods_consumption_busd", True),
            ],
        },
    }

    industries: Dict[str, Dict] = {}
    for key, spec in industry_specs.items():
        module = spec["module"]
        meta_map = module._SERIES
        computed = {}
        for series_key, higher_is_improving in spec["series"]:
            meta = meta_map.get(series_key)
            if not meta:
                continue
            computed[series_key] = _trend_for_series(
                module._fetch_series, meta["series_id"], meta["label"], meta["unit"],
                higher_is_improving=higher_is_improving,
            )
        industries[key] = {
            "label": spec["label"],
            "indicators": computed,
            **_industry_summary(list(computed.values())),
        }

    return {
        "available": True,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "attribution": real_estate_service.ATTRIBUTION,
        "macro_backdrop": {"indicators": macro_indicators},
        "industries": industries,
        "methodology_note": (
            "Each indicator's % change compares its latest observation to the "
            f"oldest of its {_TRAILING_OBS} most recent observations (exact dates "
            "given per indicator -- frequencies differ by series, so this is not a "
            "uniform calendar window). Moves under "
            f"{_FLAT_THRESHOLD_PCT}% are labelled flat. 'improving'/'worsening' "
            "reflects each indicator's own real-world direction (e.g. a falling "
            "mortgage rate is improving for housing, a falling inventory/sales "
            "ratio is improving for supply chain tightness) -- there is no "
            "combined cross-industry score; industries are not ranked against "
            "each other."
        ),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_opportunity_radar(), indent=2, ensure_ascii=False))
