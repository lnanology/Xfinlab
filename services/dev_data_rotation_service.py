"""
DEV/TEST-ONLY multi-provider OHLC rotation harness -- 2026-07-31.

NOT wired into any production API route. Nothing in api/*.py or
backend/main.py imports this module, and it must stay that way.

Why this exists: to validate, using real API responses in a local/
staging environment, that round-robin rotation across several free-tier
market-data providers can be built WITHOUT ever tripping any single
provider's own published rate limit -- i.e. the engineering pattern this
codebase would need if it ever legitimately adds Polygon.io / Twelve
Data to its data layer.

CRITICAL COMPLIANCE NOTE (see services/license_registry.py):
Polygon.io's and Twelve Data's FREE tiers are licensed for personal/
non-commercial use only and explicitly prohibit displaying or
redistributing their data to third parties (Twelve Data's ToS: "may not
display or distribute ... to third parties in any manner" on the free
plan; Polygon's Market Data ToS: any business/commercial use is
incompatible with "Non-Professional" status). XFINLAB is a commercial
product serving real end users (free and paying), so wiring either free
tier into the production request path would create the exact same class
of ToS risk this codebase already flags as "high risk" for Yahoo
Finance -- arguably a clearer violation, since both providers name
third-party display specifically in their terms.

Per an explicit 2026-07-31 decision with the user, these two providers
are therefore gated to dev/test-only usage here: this module helps prove
out the rotation/rate-limiting ENGINEERING pattern using real responses,
but must never run against real end-user traffic. Every real-network
call in this file is gated behind ALLOW_DEV_DATA_ROTATION=true (see
_dev_guard() below) -- do NOT set that env var in the Railway production
environment. If a paid Business-tier plan is ever actually purchased for
either provider, update their records in license_registry.py first, then
promote the relevant fetch function into
services/technical_analysis_service.py's real Alpaca-first/yfinance-
fallback routing -- this file should stay a harness, not become the
production path itself.

Alpaca is exempt from the gate: its free tier is already documented as
commercial-use-clean in license_registry.py and is already XFINLAB's
real production data source (see
TechnicalAnalysisService._fetch_alpaca) -- reused here as-is so the
rotator has a genuinely safe baseline provider to rotate alongside the
two dev-only ones.

Usage: run this file directly (`python services/dev_data_rotation_service.py`)
or import it from a local script/test -- never from api/*.py or
backend/main.py.
"""

import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Deque, Dict, List, Optional

import pandas as pd

from services.outbound_http import get_with_backoff
from services.technical_analysis_service import TechnicalAnalysisService

logger = logging.getLogger(__name__)

ALLOW_ENV_VAR = "ALLOW_DEV_DATA_ROTATION"

POLYGON_URL_TMPL = "https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}"
TWELVEDATA_URL = "https://api.twelvedata.com/time_series"

_PERIOD_DAYS = {"1mo": 30, "3mo": 90, "6mo": 182, "1y": 365, "2y": 730}


def _dev_guard() -> None:
    """Hard-refuses to make any Polygon/Twelve Data request unless the
    caller has explicitly opted in -- the safety net that keeps these 2
    ToS-restricted free tiers out of production even if this module is
    ever accidentally imported from somewhere it shouldn't be."""
    if os.getenv(ALLOW_ENV_VAR, "").lower() not in ("1", "true", "yes"):
        raise RuntimeError(
            f"dev_data_rotation_service is gated behind {ALLOW_ENV_VAR}=true. "
            "This module calls Polygon.io's and Twelve Data's FREE tiers, "
            "which are personal/non-commercial-use only per their own ToS "
            "(see services/license_registry.py) -- it must never run "
            "against real end-user traffic. Do not set this env var in the "
            "Railway production environment."
        )


@dataclass
class ProviderLimit:
    name: str
    calls_per_minute: int
    calls_per_day: Optional[int] = None


# Free-tier limits as published by each provider as of 2026-07-31 --
# re-verify against the provider's own docs before relying on these if
# their plan terms change.
PROVIDER_LIMITS: Dict[str, ProviderLimit] = {
    "alpaca": ProviderLimit(name="alpaca", calls_per_minute=200),
    "polygon": ProviderLimit(name="polygon", calls_per_minute=5),
    "twelvedata": ProviderLimit(name="twelvedata", calls_per_minute=8, calls_per_day=800),
}


class _RateWindow:
    """Sliding-window call tracker for one provider (per-minute AND,
    optionally, per-day) -- tells the rotator whether a provider has
    budget left RIGHT NOW, so it can skip to the next one instead of
    firing a request that would 429 the provider's free tier."""

    def __init__(self, limit: ProviderLimit):
        self.limit = limit
        self._minute_calls: Deque[float] = deque()
        self._day_calls: Deque[float] = deque()

    def _prune(self, now: float) -> None:
        while self._minute_calls and now - self._minute_calls[0] > 60:
            self._minute_calls.popleft()
        if self.limit.calls_per_day:
            while self._day_calls and now - self._day_calls[0] > 86400:
                self._day_calls.popleft()

    def has_budget(self, now: Optional[float] = None) -> bool:
        now = now if now is not None else time.time()
        self._prune(now)
        if len(self._minute_calls) >= self.limit.calls_per_minute:
            return False
        if self.limit.calls_per_day and len(self._day_calls) >= self.limit.calls_per_day:
            return False
        return True

    def record_call(self, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        self._minute_calls.append(now)
        if self.limit.calls_per_day:
            self._day_calls.append(now)

    def seconds_until_budget(self, now: Optional[float] = None) -> float:
        """How long until this provider frees up at least one call slot
        -- used to pick the soonest-available provider when all are
        currently exhausted, rather than sleeping an arbitrary amount."""
        now = now if now is not None else time.time()
        self._prune(now)
        waits = []
        if len(self._minute_calls) >= self.limit.calls_per_minute:
            waits.append(60 - (now - self._minute_calls[0]))
        if self.limit.calls_per_day and len(self._day_calls) >= self.limit.calls_per_day:
            waits.append(86400 - (now - self._day_calls[0]))
        return max(waits) if waits else 0.0


class DevProviderRotator:
    """Round-robins across registered providers, always picking the next
    one (in rotation order, continuing from wherever the last call left
    off) that currently HAS budget under its own free-tier limit; if
    every provider is exhausted, waits only as long as the soonest one
    needs before retrying -- never silently exceeds any single
    provider's published rate limit. DEV/TEST-ONLY (see module
    docstring).

    `fetch_fns` maps provider name -> a zero-arg callable that performs
    the actual real request for that provider (kept outside this class
    so this stays purely about rotation/rate-limiting logic, not any one
    provider's request format).
    """

    def __init__(self, fetch_fns: Dict[str, Callable[[], object]], order: Optional[List[str]] = None):
        unknown = set(fetch_fns) - set(PROVIDER_LIMITS)
        if unknown:
            raise ValueError(f"Unknown provider(s) with no rate limit on record: {unknown}")
        self.fetch_fns = fetch_fns
        self.order = order or list(fetch_fns.keys())
        self._windows = {name: _RateWindow(PROVIDER_LIMITS[name]) for name in self.order}
        self._next_idx = 0

    def fetch(self, max_wait_seconds: float = 30.0):
        """Try each provider in rotation order starting from wherever we
        left off last call (true round-robin, not always-provider-A-
        first) until one has budget; if none do, sleep for the soonest
        provider's free-up time (capped at max_wait_seconds) and retry."""
        deadline = time.time() + max_wait_seconds
        while True:
            now = time.time()
            for offset in range(len(self.order)):
                idx = (self._next_idx + offset) % len(self.order)
                name = self.order[idx]
                window = self._windows[name]
                if window.has_budget(now):
                    window.record_call(now)
                    self._next_idx = (idx + 1) % len(self.order)
                    try:
                        result = self.fetch_fns[name]()
                        return name, result
                    except Exception:
                        logger.exception("dev rotation: provider %s call failed", name)
                        continue
            wait = min(w.seconds_until_budget(now) for w in self._windows.values())
            wait = max(0.5, min(wait, deadline - now))
            if now + wait > deadline:
                raise TimeoutError("All dev providers exhausted their free-tier budget within max_wait_seconds")
            time.sleep(wait)


def _fetch_alpaca_dev(symbol: str, period: str = "6mo", interval: str = "1d") -> Optional[pd.DataFrame]:
    """Reuses the SAME Alpaca client already used in production -- Alpaca's
    free tier is already commercial-use-clean per license_registry.py, so
    no _dev_guard() gate needed here beyond the usual missing-key
    fallback (returns None, same as the production code path)."""
    api_key = os.getenv("ALPACA_API_KEY_ID")
    api_secret = os.getenv("ALPACA_API_SECRET_KEY")
    if not api_key or not api_secret:
        return None
    return TechnicalAnalysisService._fetch_alpaca(symbol.upper(), period, interval, api_key, api_secret)


def _fetch_polygon_dev(symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    """DEV/TEST ONLY -- see module docstring. Polygon's free 'Basic' tier:
    end-of-day daily aggregate bars, 5 calls/minute, personal/non-
    commercial ToS."""
    _dev_guard()
    api_key = os.getenv("POLYGON_API_KEY")
    if not api_key:
        return None
    days = _PERIOD_DAYS.get(period, 182)
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    url = POLYGON_URL_TMPL.format(symbol=symbol.upper(), start=start.isoformat(), end=end.isoformat())
    res = get_with_backoff(
        url, params={"apiKey": api_key, "adjusted": "true", "sort": "asc", "limit": 5000}, timeout=15
    )
    res.raise_for_status()
    results = res.json().get("results") or []
    if not results:
        logger.info("Polygon (dev) returned no results for %s", symbol)
        return None
    df = pd.DataFrame(results)
    df["t"] = pd.to_datetime(df["t"], unit="ms")
    df = df.set_index("t").rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
    return df[["Open", "High", "Low", "Close", "Volume"]]


def _fetch_twelvedata_dev(symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    """DEV/TEST ONLY -- see module docstring. Twelve Data's free tier:
    8 calls/minute, 800 calls/day, personal/non-commercial ToS."""
    _dev_guard()
    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key:
        return None
    days = _PERIOD_DAYS.get(period, 182)
    outputsize = min(days, 5000)
    res = get_with_backoff(
        TWELVEDATA_URL,
        params={"symbol": symbol.upper(), "interval": "1day", "outputsize": outputsize, "apikey": api_key},
        timeout=15,
    )
    res.raise_for_status()
    payload = res.json()
    values = payload.get("values")
    if not values:
        logger.info("Twelve Data (dev) returned no values for %s: %s", symbol, payload.get("message"))
        return None
    df = pd.DataFrame(values)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").rename(
        columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    )
    df = df.astype({"Open": float, "High": float, "Low": float, "Close": float, "Volume": float})
    return df.sort_index()[["Open", "High", "Low", "Close", "Volume"]]


if __name__ == "__main__":
    # Standalone smoke test -- only runs when this file is executed
    # directly (e.g. `python services/dev_data_rotation_service.py`),
    # never on any import path used by the running API server. Requires
    # ALLOW_DEV_DATA_ROTATION=true plus whichever provider API keys you
    # want to actually exercise; providers with no key configured just
    # return None and get skipped by the rotator's own has_budget/result
    # handling (a None result is still "handled", not an exception).
    logging.basicConfig(level=logging.INFO)
    test_symbol = os.getenv("DEV_ROTATION_TEST_SYMBOL", "AAPL")

    rotator = DevProviderRotator({
        "alpaca": lambda: _fetch_alpaca_dev(test_symbol),
        "polygon": lambda: _fetch_polygon_dev(test_symbol),
        "twelvedata": lambda: _fetch_twelvedata_dev(test_symbol),
    })

    for i in range(6):
        provider, df = rotator.fetch()
        rows = 0 if df is None else len(df)
        print(f"call {i}: served by {provider} -> {rows} rows")
