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

2026-08-31 follow-up (AJ: "擴展覆蓋 energy+agriculture"): added EIA
(energy) and USDA (agriculture) as a 4th and 5th industry. Both use a
different fetch shape than the 3 FRED-style modules above -- EIA's
_fetch_series(series_key, n_obs) takes its own internal dict key
rather than the external series_id, and returns {"period", "value"}
not {"date", "value"}; USDA's get_snapshot()/get_agriculture_context_
for_ticker() only ever exposed a single latest point, so this module
added a new usda_agriculture_service._fetch_history(series_key, n_obs)
function (same file, same fallback chain) that reuses USDA's existing
Quick Stats request -- which already returns every available year, not
just the latest -- and keeps the whole window instead of discarding
all but the newest row. _trend_for_series() below now takes a
`date_key` param ("date" for FRED-shape, "period" for EIA/USDA-shape)
and industry_specs carries a per-industry `id_mode` (whether to look
the fetch function up by the module's own external series_id, or by
the internal dict key) so one generic loop still drives all 5
industries without a copy-pasted branch per shape.

Each industry now also gates independently on its OWN source's env var
(FRED_API_KEY / EIA_API_KEY / USDA_NASS_API_KEY) rather than the whole
endpoint going dark if just one is unset -- an industry with a missing
key reports zero indicators and an honest "not configured" summary,
same shape as a fully-computed industry, rather than 503ing the entire
response over one missing key. Overall `available` is only False if
literally none of the 3 keys are set.

Scope, stated honestly: still no combined cross-industry score --
adding 2 more industries makes that even less defensible, not more.

Zero new API integration, zero new signup for the 3 original
industries: reuses the same FRED-backed modules already live and
gated behind FRED_API_KEY. Energy/agriculture reuse the EIA/USDA
Data Factory collectors that were already live and gated behind their
own keys before this module existed. This module itself fetches
nothing new directly -- it only re-calls each existing module's own
fetch function, inheriting that module's cache/persistence/fallback
chain, same "zero new data source" convention as Company Network
Phase 4's crossholdings re-query.
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
                       higher_is_improving: bool, date_key: str = "date") -> Optional[Dict]:
    """Fetches _TRAILING_OBS observations via the given module's own
    fetch function and returns a real, computed % change between the
    oldest and latest point in that window -- None if fewer than 2
    usable observations exist (never fabricates a change from a single
    point).

    `date_key`: the observation dict's date field name -- "date" for the
    3 FRED-style modules, "period" for EIA/USDA (see module docstring).
    Only the field name differs; the meaning (an ISO-ish date/year
    string for that observation) is the same.

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
        "latest_date": latest[date_key],
        "latest_value": latest["value"],
        "compare_date": oldest[date_key],
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
            "energy": {...},
            "agriculture": {...},
         },
         "methodology_note": "..."}
        or {"available": False, "message": "..."} only if NONE of
        FRED_API_KEY / EIA_API_KEY / USDA_NASS_API_KEY are set.

    2026-08-31: each industry now gates independently on its own
    source's key -- real_estate/supply_chain/consumer_demand need
    FRED_API_KEY, energy needs EIA_API_KEY, agriculture needs
    USDA_NASS_API_KEY. An industry whose key is missing still appears
    in the response with an empty indicators dict and an honest "not
    configured" summary (same shape as a fully-computed industry) --
    it does not take the whole endpoint down. Macro backdrop stays
    FRED-gated (all 4 macro series are FRED series).
    """
    from services import (
        real_estate_service, supply_chain_service, consumer_demand_service,
        fred_macro_service, eia_energy_service, usda_agriculture_service,
    )

    fred_ok = real_estate_service.is_available()
    eia_ok = eia_energy_service.is_available()
    usda_ok = usda_agriculture_service.is_available()

    if not (fred_ok or eia_ok or usda_ok):
        return {"available": False, "message": "FRED_API_KEY / EIA_API_KEY / USDA_NASS_API_KEY 都未設定，Opportunity Radar 暫時未開放。"}

    # Macro backdrop -- higher_is_improving is deliberately omitted here
    # (left as direction only, no improving/worsening label) because
    # "is rising unemployment bad" etc. depends on where in the cycle you
    # are -- unlike the industry indicators below, these don't have a
    # single always-true improving direction, so labelling one would be
    # editorializing, not reporting. Direction (up/down/flat) is still a
    # plain fact. FRED-gated (all 4 series here are FRED series).
    macro_indicators = {}
    if fred_ok:
        macro_specs = [
            ("fed_funds_rate_pct", "FEDFUNDS", "Federal Funds Rate", "%"),
            ("unemployment_pct", "UNRATE", "Unemployment Rate", "%"),
            ("yield_curve_10y2y_pct", "T10Y2Y", "10Y-2Y Treasury Yield Spread", "%"),
            ("jobless_claims_initial", "ICSA", "Initial Jobless Claims", "claims"),
        ]
        for key, series_id, label, unit in macro_specs:
            t = _trend_for_series(fred_macro_service._fetch_series, series_id, label, unit, higher_is_improving=True)
            if t:
                t.pop("improving", None)  # direction-only for macro, see note above
            macro_indicators[key] = t

    # Industry verticals -- higher_is_improving is a factual property of
    # each series (documented inline), not a subjective call.
    #
    # id_mode: "series_id" looks the fetch function up by the module's own
    # external series_id (meta["series_id"]) -- the 3 FRED-shape modules.
    # "dict_key" passes the internal _SERIES dict key straight through --
    # EIA's _fetch_series() and USDA's _fetch_history() both take their
    # own internal key rather than an external series id (see module
    # docstring above for why).
    # date_key: the observation dict's date field name for this module.
    industry_specs = {
        "real_estate": {
            "module": real_estate_service, "label": "Real Estate",
            "gate": fred_ok, "env_label": "FRED_API_KEY",
            "fetch_attr": "_fetch_series", "id_mode": "series_id", "date_key": "date",
            "series": [
                ("mortgage_rate_30y_pct", False),   # lower financing cost = improving for the sector
                ("home_price_index", True),
                ("housing_starts_thousands", True),
                ("existing_home_sales_thousands", True),
            ],
        },
        "supply_chain": {
            "module": supply_chain_service, "label": "Supply Chain / Manufacturing",
            "gate": fred_ok, "env_label": "FRED_API_KEY",
            "fetch_attr": "_fetch_series", "id_mode": "series_id", "date_key": "date",
            "series": [
                ("inventory_sales_ratio", False),   # falling ratio = tighter availability/restocking demand
                ("manufacturing_new_orders_musd", True),
                ("durable_goods_orders_musd", True),
                ("industrial_production_manufacturing_index", True),
                ("manufacturing_employment_thousands", True),
            ],
        },
        "consumer_demand": {
            "module": consumer_demand_service, "label": "Consumer Demand / Retail",
            "gate": fred_ok, "env_label": "FRED_API_KEY",
            "fetch_attr": "_fetch_series", "id_mode": "series_id", "date_key": "date",
            "series": [
                ("retail_sales_total_musd", True),
                ("retail_sales_goods_only_musd", True),
                ("personal_consumption_expenditures_busd", True),
                ("durable_goods_consumption_busd", True),
            ],
        },
        "energy": {
            "module": eia_energy_service, "label": "Energy",
            "gate": eia_ok, "env_label": "EIA_API_KEY",
            "fetch_attr": "_fetch_series", "id_mode": "dict_key", "date_key": "period",
            "series": [
                # Rising spot price = improving for energy producers
                # (higher realized revenue per barrel/MMBTU) -- same
                # "industry's own business health" framing as mortgage
                # rate/inventory ratio above, not a consumer-price read.
                ("wti_crude_spot_usd_bbl", True),
                ("henry_hub_natgas_spot_usd_mmbtu", True),
                # Rising storage = an oversupply signal, typically bearish
                # for producer pricing power -- falling storage is the
                # improving direction here, mirroring inventory_sales_ratio.
                ("natgas_storage_lower48_bcf", False),
            ],
        },
        "agriculture": {
            "module": usda_agriculture_service, "label": "Agriculture",
            "gate": usda_ok, "env_label": "USDA_NASS_API_KEY",
            "fetch_attr": "_fetch_history", "id_mode": "dict_key", "date_key": "period",
            "series": [
                # Rising price received = improving for farmers (more
                # revenue per bushel) -- USDA's own price-received framing.
                ("corn_price_received_usd_bu", True),
                ("wheat_price_received_usd_bu", True),
                ("soybeans_price_received_usd_bu", True),
            ],
        },
    }

    industries: Dict[str, Dict] = {}
    attributions: List[str] = []
    for key, spec in industry_specs.items():
        if not spec["gate"]:
            industries[key] = {
                "label": spec["label"],
                "indicators": {},
                "indicators_available": 0,
                "improving_count": 0,
                "worsening_count": 0,
                "flat_count": 0,
                "summary": f"{spec['env_label']} 未設定，{spec['label']} 暫時未開放 -- not configured, temporarily unavailable.",
            }
            continue

        module = spec["module"]
        if getattr(module, "ATTRIBUTION", None) and module.ATTRIBUTION not in attributions:
            attributions.append(module.ATTRIBUTION)
        meta_map = module._SERIES
        fetch_fn = getattr(module, spec["fetch_attr"])
        computed = {}
        for series_key, higher_is_improving in spec["series"]:
            meta = meta_map.get(series_key)
            if not meta:
                continue
            lookup_id = meta["series_id"] if spec["id_mode"] == "series_id" else series_key
            computed[series_key] = _trend_for_series(
                fetch_fn, lookup_id, meta["label"], meta["unit"],
                higher_is_improving=higher_is_improving, date_key=spec["date_key"],
            )
        industries[key] = {
            "label": spec["label"],
            "indicators": computed,
            **_industry_summary(list(computed.values())),
        }

    return {
        "available": True,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "attribution": " | ".join(attributions) if attributions else real_estate_service.ATTRIBUTION,
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
            "ratio is improving for supply chain tightness, a rising WTI/Henry "
            "Hub spot price is improving for energy producers) -- there is no "
            "combined cross-industry score; industries are not ranked against "
            "each other. An industry whose data source key isn't configured "
            "reports zero indicators and an honest note, not a guess."
        ),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_opportunity_radar(), indent=2, ensure_ascii=False))
