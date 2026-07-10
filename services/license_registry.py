"""
License Registry — XFINLAB Architecture, Phase 1.

Central, single-source-of-truth list of every external data source's
licensing status. This is pure bookkeeping: it does NOT change any live
request behaviour by itself. Its job is to make "can we legally use this
data source, and how?" a one-line lookup instead of institutional
knowledge that lives in someone's head.

Directly addresses the known risk: Yahoo Finance (via yfinance) is used
for market data but its terms of service do not grant a commercial-use
license — this registry documents that clearly so it can't get lost, and
gives future data-source swaps a checklist to fill in.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class LicenseRecord:
    source_id: str
    license_type: str  # "commercial" | "non_commercial" | "unknown" | "public_domain"
    commercial_use_allowed: bool
    terms_url: Optional[str] = None
    risk_level: str = "unknown"  # "low" | "medium" | "high"
    notes: str = ""
    replacement_candidates: List[str] = field(default_factory=list)


# --- Registry data ---
# Add a new entry here whenever a new external data source is introduced
# anywhere in the codebase (market data, news, crypto, etc).
_LICENSES: Dict[str, LicenseRecord] = {
    "yahoo_finance": LicenseRecord(
        source_id="yahoo_finance",
        license_type="non_commercial",
        commercial_use_allowed=False,
        terms_url="https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
        risk_level="high",
        notes=(
            "Accessed via the unofficial `yfinance` Python library, which "
            "scrapes Yahoo Finance's public endpoints. Yahoo's own ToS does "
            "not grant a commercial-use license for this data. XFINLAB is a "
            "commercial product, so this is a known legal risk that should "
            "be resolved before scaling paid usage. Currently used in "
            "services/market_data_service.py and services/"
            "technical_analysis_service.py."
        ),
        replacement_candidates=[
            "polygon_io", "twelve_data", "finnhub", "eod_historical_data", "alpaca_markets",
        ],
    ),
}


def get_license(source_id: str) -> Optional[LicenseRecord]:
    return _LICENSES.get(source_id)


def list_licenses() -> List[LicenseRecord]:
    return list(_LICENSES.values())


def list_high_risk_sources() -> List[LicenseRecord]:
    """Sources that should be prioritised for replacement or a paid plan."""
    return [r for r in _LICENSES.values() if r.risk_level == "high"]


def register_license(record: LicenseRecord) -> None:
    """Add or update a license record. Call this when a new data source is
    introduced anywhere in the codebase, so the registry never drifts out
    of sync with reality."""
    _LICENSES[record.source_id] = record


if __name__ == "__main__":
    for rec in list_high_risk_sources():
        print(f"[HIGH RISK] {rec.source_id}: {rec.notes}")
