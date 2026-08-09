"""
ECB (European Central Bank) Macro Service -- 2026-08-09, World Engine
Phase 0 (XFINLAB_Final_Strategy.md section 5/7).

Same rationale as services/fred_macro_service.py, for the Eurozone
instead of the US: services/macro_data_service.py represents "europe" via
World Bank's UK figures (a proxy, since "Europe" isn't a single World
Bank entity) at annual frequency. The ECB's own SDMX 2.1 REST API
publishes actual Eurozone-aggregate (not single-country-proxy) figures at
monthly frequency for inflation and near-real-time for policy rates, with
no API key required.

Terms (from license_registry.py's "ecb_data_portal" entry, verified
2026-07-31 at ecb.europa.eu/services/disclaimer): free to reuse, subject
to (1) citing the ECB as source wherever shown -- see `attribution` field
below -- and (2) since XFINLAB is a paid product, disclosing that this
data is available free of charge from the ECB directly, both before
payment and each time it's accessed -- satisfied by that same
`attribution` field being present on every response returned to API
callers (dev.xfinlab.com's methodology page carries the full text).

No dormant-until-configured gate needed here (no signup, no key) --
unlike fred_macro_service.py, this is live the moment it deploys.

Honesty contract: any fetch/parse failure returns {"available": False},
never a fabricated number. ECB's SDMX CSV omits a row entirely for a
missing observation rather than marking it -- so "no row" is already the
only "missing" signal, nothing to special-case.
"""

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from services.outbound_http import get_with_backoff

logger = logging.getLogger(__name__)

ECB_BASE_URL = "https://data-api.ecb.europa.eu/service/data"
ATTRIBUTION = "Source: European Central Bank (ECB) Data Portal. This data is available free of charge directly from the ECB at data.ecb.europa.eu."

# (flowRef, series key) pairs -- SDMX dataflow/dimension identifiers,
# stable ECB reference series:
#   FM.D.U2.EUR.4F.KR.MRR_FR.LEV   -- ECB main refinancing operations rate, daily
#   ICP.M.U2.N.000000.4.ANR        -- Eurozone HICP (headline inflation), YoY %, monthly
_SERIES = {
    "refi_rate_pct": ("FM", "D.U2.EUR.4F.KR.MRR_FR.LEV"),
    "hicp_inflation_yoy_pct": ("ICP", "M.U2.N.000000.4.ANR"),
}

_CACHE_TTL_SECONDS = 6 * 3600
_cache: Dict[str, Dict] = {}  # "flowRef.key" -> {"fetched_at": epoch, "observation": {...}}


def _fetch_latest(flow_ref: str, key: str) -> Optional[Dict]:
    cache_key = f"{flow_ref}.{key}"
    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(cache_key)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["observation"]

    url = f"{ECB_BASE_URL}/{flow_ref}/{key}"
    try:
        res = get_with_backoff(
            url,
            params={"lastNObservations": 1, "format": "csvdata"},
            headers={"Accept": "text/csv"},
            timeout=10,
        )
        if res.status_code != 200:
            logger.info("ecb_macro_service: %s/%s returned HTTP %s", flow_ref, key, res.status_code)
            return cached["observation"] if cached else None
        rows = list(csv.DictReader(io.StringIO(res.text)))
    except Exception as e:
        logger.info("ecb_macro_service: failed to fetch %s/%s: %s", flow_ref, key, e)
        return cached["observation"] if cached else None

    if not rows:
        return cached["observation"] if cached else None

    last_row = rows[-1]
    raw_value = last_row.get("OBS_VALUE")
    raw_period = last_row.get("TIME_PERIOD")
    if raw_value in (None, ""):
        return cached["observation"] if cached else None

    try:
        observation = {"date": raw_period, "value": round(float(raw_value), 3)}
    except (TypeError, ValueError):
        return cached["observation"] if cached else None

    _cache[cache_key] = {"fetched_at": now, "observation": observation}
    return observation


def get_eurozone_snapshot() -> Dict:
    """
    Returns:
        {"available": True, "as_of": "...", "attribution": "...",
         "indicators": {
            "refi_rate_pct": {"date": "2026-08-08", "value": 3.15} or None,
            "hicp_inflation_yoy_pct": {"date": "2026-07-01", "value": 2.2} or None,
         }}
        {"available": False, "message": "..."} -- both series failed
            (transient ECB outage). Partial failure (one series OK)
            still returns available:True, same graceful-degradation
            convention as macro_data_service.py / fred_macro_service.py.
    """
    indicators = {}
    for key, (flow_ref, series_key) in _SERIES.items():
        indicators[key] = _fetch_latest(flow_ref, series_key)

    if all(v is None for v in indicators.values()):
        return {"available": False, "message": "ECB暫時未能回應（可能係短暫故障）。"}

    return {
        "available": True,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "attribution": ATTRIBUTION,
        "indicators": indicators,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_eurozone_snapshot(), indent=2, ensure_ascii=False))
