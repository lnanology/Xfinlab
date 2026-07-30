"""
Market Data Gateway -- 2026-07-31.

Formalizes the "single entry point, AI never knows which provider
served it" pattern from the user's Market Data Gateway proposal.

IMPORTANT: this is an ADDITIVE wrapper, not a rewrite. It does not
change any existing behavior -- `get_ohlc()` below just delegates
straight through to TechnicalAnalysisService.fetch_ohlc_history(), which
already implements the real routing (Alpaca-first for US symbols when
keys are configured, yfinance fallback otherwise -- see
services/technical_analysis_service.py). Every existing call site that
already calls fetch_ohlc_history() directly keeps working exactly as
before; nothing was moved or removed. This module exists so that:

  1. New code has one obvious place to import from
     (`from services.market_data_gateway import get_ohlc`) instead of
     reaching into TechnicalAnalysisService's internals.
  2. There is one documented, inspectable registry (PROVIDERS below) of
     every OHLC provider this codebase knows about -- including the ones
     NOT currently live in production -- so the next person (or the next
     session) doesn't have to go re-derive "which providers are actually
     wired in vs. just sitting in a dev harness" from scratch.
  3. If/when a provider's status changes (e.g. a paid Polygon or Twelve
     Data plan gets purchased), THIS file is where that gets promoted --
     update PROVIDERS' `enabled` flag and swap get_ohlc()'s body to
     route through it, rather than hunting across the codebase for every
     place that might need to know about the new provider.

Provider statuses as of 2026-07-31 (see services/license_registry.py for
the full legal detail behind each):
  - alpaca:      LIVE in production. Free tier, commercial-use-clean.
  - yfinance:    LIVE in production, as the fallback when Alpaca has no
                 keys / isn't applicable (non-US symbol, unsupported
                 interval) / errors. Documented HIGH RISK (Yahoo's ToS
                 doesn't grant commercial use) -- kept only because
                 removing it with no replacement would break coverage
                 for every non-US-equity symbol XFINLAB supports today.
  - polygon:     NOT live. Free tier is personal/non-commercial-use only
                 per Polygon's own Market Data ToS. Real fetch function
                 exists in services/dev_data_rotation_service.py, gated
                 behind ALLOW_DEV_DATA_ROTATION=true, dev/test-only.
  - twelvedata:  NOT live. Same reasoning as polygon (Twelve Data's free
                 tier explicitly bars third-party display). Same
                 dev-only gating.
"""

import logging
from typing import Callable, Dict, Optional

import pandas as pd

from services.technical_analysis_service import fetch_ohlc_history as _fetch_ohlc_history

logger = logging.getLogger(__name__)


def _polygon_fetch_fn() -> Optional[Callable]:
    """Lazily imported -- services/dev_data_rotation_service.py itself
    imports TechnicalAnalysisService, so importing it eagerly at module
    load time here would be a needless import-time coupling for a
    provider that (as of this entry) is never actually enabled."""
    from services.dev_data_rotation_service import _fetch_polygon_dev
    return _fetch_polygon_dev


def _twelvedata_fetch_fn() -> Optional[Callable]:
    from services.dev_data_rotation_service import _fetch_twelvedata_dev
    return _fetch_twelvedata_dev


PROVIDERS: Dict[str, Dict] = {
    "alpaca": {
        "enabled": True,
        "commercial_clean": True,
        "license_id": "alpaca_markets",
        "notes": "Live production source for US-listed symbols when ALPACA_API_KEY_ID/ALPACA_API_SECRET_KEY are set.",
    },
    "yfinance": {
        "enabled": True,
        "commercial_clean": False,
        "license_id": "yahoo_finance",
        "notes": "Live production fallback -- documented high-risk, kept for coverage until a compliant replacement exists for non-US/unsupported-interval requests.",
    },
    "polygon": {
        "enabled": False,
        "commercial_clean": False,
        "license_id": "polygon_io",
        "notes": "Free tier is personal/non-commercial-use only. Dev/test-only via services/dev_data_rotation_service.py (ALLOW_DEV_DATA_ROTATION=true). Requires a paid Business-tier plan before enabling here.",
        "fetch_fn_factory": _polygon_fetch_fn,
    },
    "twelvedata": {
        "enabled": False,
        "commercial_clean": False,
        "license_id": "twelve_data",
        "notes": "Free tier explicitly bars third-party display. Dev/test-only via services/dev_data_rotation_service.py (ALLOW_DEV_DATA_ROTATION=true). Requires a paid Business plan before enabling here.",
        "fetch_fn_factory": _twelvedata_fetch_fn,
    },
}


def list_providers() -> Dict[str, Dict]:
    """Introspectable status of every OHLC provider this codebase knows
    about (for an admin panel, a docs page, or just a future session
    asking 'what do we actually have wired up right now')."""
    return {
        name: {k: v for k, v in cfg.items() if k != "fetch_fn_factory"}
        for name, cfg in PROVIDERS.items()
    }


def get_ohlc(symbol: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """
    THE single entry point for OHLC data. Callers never need to know
    which provider actually served the request -- exactly the "AI only
    calls /market/AAPL" abstraction from the user's proposal.

    Delegates directly to the existing, already-battle-tested
    Alpaca-first/yfinance-fallback routing in
    services.technical_analysis_service.fetch_ohlc_history() -- this
    function adds no new logic of its own, on purpose, so introducing
    this gateway carries zero behavioral risk to production.
    """
    return _fetch_ohlc_history(symbol, period=period, interval=interval)


if __name__ == "__main__":
    import json
    print(json.dumps(list_providers(), indent=2, default=str))
