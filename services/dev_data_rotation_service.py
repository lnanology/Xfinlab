"""
DEV/TEST-ONLY multi-provider OHLC rotation harness -- 2026-07-31.

NOT wired into any production API route. Nothing in api/*.py or
backend/main.py imports this module, and it must stay that way.

Why this exists: to validate, using real API responses in a local/
staging environment, that round-robin rotation across several free-tier
market-data providers can be built WITHOUT ever tripping any single
provider's own published rate limit -- i.e. the engineering pattern this
codebase would need if it ever legitimately adds Polygon.io / Twelve
Data / Finnhub / Marketstack to its data layer.

CRITICAL COMPLIANCE NOTE (see services/license_registry.py):
Polygon.io's and Twelve Data's FREE tiers are licensed for personal/
non-commercial use only and explicitly prohibit displaying or
redistributing their data to third parties (Twelve Data's ToS: "may not
display or distribute ... to third parties in any manner" on the free
plan; Polygon's Market Data ToS: any business/commercial use is
incompatible with "Non-Professional" status).

Marketstack (2026-07-31 addition): confirmed via their own public
pricing page (marketstack.com/pricing) -- "Commercial Use" is listed as
a named, checked feature starting at the paid Basic plan ($9.99/mo) and
above; it is explicitly ABSENT from the Free plan's feature list. This
is the clearest signal found for any provider checked this session --
not an inference from a sales-contact link, but a literal named feature
gated to paid tiers on the provider's own site.

Finnhub (2026-07-31 addition): could not access Finnhub's actual Terms
of Service text directly (client-rendered SPA blocked both WebFetch and
WebSearch from seeing the real page content, and no browser tool was
available to render it). Circumstantial evidence -- their FAQ's
noncommittal "review the terms before commercial use" wording, and
multiple third-party sources noting Finnhub routes commercial inquiries
to sales@finnhub.io for a "commercial license" -- points the same
direction as Polygon/Twelve Data/Marketstack, but this is NOT a
confirmed reading of primary-source ToS text the way the other three
are. Treated with the same dev-only caution regardless, since the
signal is consistently in one direction and this codebase's convention
is to assume the more conservative reading when actual ToS text can't be
verified.

BaoStock (2026-07-31 addition): a free, no-registration Python client for
China A-share history -- fills a real gap, since services/
market_data_gateway.py has zero A-share coverage today. The wrapper
LIBRARY is BSD-licensed (confirmed via PyPI/GitHub PKG-INFO), but same as
Finnhub above, this codebase could NOT independently verify BaoStock's
own data-terms page (baostock.com is a client-rendered SPA that blocked
both WebFetch and WebSearch, and no browser-rendering tool was available
in that session) -- a permissive code license does not by itself confirm
the underlying A-share DATA can be redistributed commercially. Treated
with the same conservative unknown/high-risk rating as Finnhub. Also
architecturally different from the other four: it's a stateful login/
query/logout session against BaoStock's own data server, not a metered
HTTP API, so there's no official per-minute/per-day figure to record --
the limit registered for it below is a precautionary self-imposed
number, not a provider-published one.

XFINLAB is a commercial product serving real end users (free and
paying), so wiring any of these five free sources into the production
request path would create the exact same class of ToS risk this
codebase already flags as "high risk" for Yahoo Finance.

Per explicit 2026-07-31 decisions with the user (extended from Polygon/
Twelve Data to also cover Finnhub, Marketstack, and BaoStock), all five
providers are therefore gated to dev/test-only usage here: this module
helps prove out the rotation/rate-limiting ENGINEERING pattern using real
responses, but must never run against real end-user traffic. Every
real-network call in this file is gated behind ALLOW_DEV_DATA_ROTATION=true
(see _dev_guard() below) -- do NOT set that env var in the Railway
production environment. If a paid Business/commercial-tier plan is ever
actually purchased for any of these providers (or BaoStock's actual data
terms are confirmed acceptable), update its record in license_registry.py
first, then promote the relevant fetch function into services/
technical_analysis_service.py's real Alpaca-first/yfinance-fallback
routing -- this file should stay a harness, not become the production
path itself.

Alpaca is exempt from the gate: its free tier is already documented as
commercial-use-clean in license_registry.py and is already XFINLAB's
real production data source (see
TechnicalAnalysisService._fetch_alpaca) -- reused here as-is so the
rotator has a genuinely safe baseline provider to rotate alongside the
dev-only ones.

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
FINNHUB_CANDLE_URL = "https://finnhub.io/api/v1/stock/candle"
MARKETSTACK_EOD_URL = "https://api.marketstack.com/v1/eod"

_PERIOD_DAYS = {"1mo": 30, "3mo": 90, "6mo": 182, "1y": 365, "2y": 730}


def _dev_guard() -> None:
    """Hard-refuses to make any Polygon/Twelve Data/Finnhub/Marketstack/
    BaoStock request unless the caller has explicitly opted in -- the
    safety net that keeps these ToS-restricted (or ToS-unconfirmed, see
    Finnhub's and BaoStock's module-docstring notes) free sources out of
    production even if this module is ever accidentally imported from
    somewhere it shouldn't be."""
    if os.getenv(ALLOW_ENV_VAR, "").lower() not in ("1", "true", "yes"):
        raise RuntimeError(
            f"dev_data_rotation_service is gated behind {ALLOW_ENV_VAR}=true. "
            "This module calls Polygon.io's, Twelve Data's, Finnhub's, "
            "Marketstack's, and BaoStock's FREE sources, which are personal/"
            "non-commercial-use only (or unconfirmed for commercial use) per "
            "their own terms (see services/license_registry.py) -- it must "
            "never run against real end-user traffic. Do not set this env "
            "var in the Railway production environment."
        )


@dataclass
class ProviderLimit:
    name: str
    # calls_per_minute is the common case (per-minute-metered free tiers).
    # Optional so a provider whose binding constraint is a MONTHLY quota
    # (e.g. Marketstack: 100 requests/month, no published per-minute cap)
    # can be registered without inventing an unpublished per-minute number.
    calls_per_minute: Optional[int] = None
    calls_per_day: Optional[int] = None
    calls_per_month: Optional[int] = None

    def __post_init__(self):
        if not any([self.calls_per_minute, self.calls_per_day, self.calls_per_month]):
            raise ValueError(f"ProviderLimit({self.name}) needs at least one of "
                              "calls_per_minute/calls_per_day/calls_per_month set")


# Free-tier limits as published by each provider as of 2026-07-31 --
# re-verify against the provider's own docs before relying on these if
# their plan terms change.
PROVIDER_LIMITS: Dict[str, ProviderLimit] = {
    "alpaca": ProviderLimit(name="alpaca", calls_per_minute=200),
    "polygon": ProviderLimit(name="polygon", calls_per_minute=5),
    "twelvedata": ProviderLimit(name="twelvedata", calls_per_minute=8, calls_per_day=800),
    # Finnhub's free tier is published as 60 calls/minute (see module
    # docstring for the commercial-use-terms caveat).
    "finnhub": ProviderLimit(name="finnhub", calls_per_minute=60),
    # Marketstack's Free plan is a strict 100 REQUESTS PER MONTH -- no
    # published per-minute cap exists for it, so calls_per_minute is left
    # unset here rather than inventing one; calls_per_month is the real
    # binding constraint (confirmed via marketstack.com/faq: "Free Plan
    # that will allow users to make up to 100 market data API requests
    # per month").
    "marketstack": ProviderLimit(name="marketstack", calls_per_month=100),
    # BaoStock (2026-07-31): unlike every other entry above, this number
    # is NOT sourced from the provider's own published docs -- BaoStock is
    # a free, no-registration, stateful login/query/logout client with no
    # officially published rate limit anywhere found. 30/minute is a
    # precautionary self-imposed cap this codebase is choosing so the dev
    # harness never hammers their server; lower it further if they ever
    # push back.
    "baostock": ProviderLimit(name="baostock", calls_per_minute=30),
}


class _RateWindow:
    """Sliding-window call tracker for one provider (per-minute, per-day,
    and/or per-month, whichever the provider's ProviderLimit sets) --
    tells the rotator whether a provider has budget left RIGHT NOW, so it
    can skip to the next one instead of firing a request that would 429
    the provider's free tier or blow through a monthly quota."""

    _MONTH_SECONDS = 30 * 86400  # rolling 30-day window, not calendar-month
    # reset -- same "sliding window, not calendar reset" convention as the
    # existing per-day tracking below, simpler and never UNDER-counts a
    # calendar month's usage the way a naive "resets on the 1st" tracker
    # could if the caller runs across a month boundary.

    def __init__(self, limit: ProviderLimit):
        self.limit = limit
        self._minute_calls: Deque[float] = deque()
        self._day_calls: Deque[float] = deque()
        self._month_calls: Deque[float] = deque()

    def _prune(self, now: float) -> None:
        if self.limit.calls_per_minute:
            while self._minute_calls and now - self._minute_calls[0] > 60:
                self._minute_calls.popleft()
        if self.limit.calls_per_day:
            while self._day_calls and now - self._day_calls[0] > 86400:
                self._day_calls.popleft()
        if self.limit.calls_per_month:
            while self._month_calls and now - self._month_calls[0] > self._MONTH_SECONDS:
                self._month_calls.popleft()

    def has_budget(self, now: Optional[float] = None) -> bool:
        now = now if now is not None else time.time()
        self._prune(now)
        if self.limit.calls_per_minute and len(self._minute_calls) >= self.limit.calls_per_minute:
            return False
        if self.limit.calls_per_day and len(self._day_calls) >= self.limit.calls_per_day:
            return False
        if self.limit.calls_per_month and len(self._month_calls) >= self.limit.calls_per_month:
            return False
        return True

    def record_call(self, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        if self.limit.calls_per_minute:
            self._minute_calls.append(now)
        if self.limit.calls_per_day:
            self._day_calls.append(now)
        if self.limit.calls_per_month:
            self._month_calls.append(now)

    def seconds_until_budget(self, now: Optional[float] = None) -> float:
        """How long until this provider frees up at least one call slot
        -- used to pick the soonest-available provider when all are
        currently exhausted, rather than sleeping an arbitrary amount."""
        now = now if now is not None else time.time()
        self._prune(now)
        waits = []
        if self.limit.calls_per_minute and len(self._minute_calls) >= self.limit.calls_per_minute:
            waits.append(60 - (now - self._minute_calls[0]))
        if self.limit.calls_per_day and len(self._day_calls) >= self.limit.calls_per_day:
            waits.append(86400 - (now - self._day_calls[0]))
        if self.limit.calls_per_month and len(self._month_calls) >= self.limit.calls_per_month:
            waits.append(self._MONTH_SECONDS - (now - self._month_calls[0]))
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


def _fetch_finnhub_dev(symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    """DEV/TEST ONLY -- see module docstring. Finnhub's free tier: daily
    candles via /stock/candle, 60 calls/minute, commercial-use terms not
    independently confirmed (treated conservatively, same as Polygon/
    Twelve Data)."""
    _dev_guard()
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        return None
    days = _PERIOD_DAYS.get(period, 182)
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    res = get_with_backoff(
        FINNHUB_CANDLE_URL,
        params={
            "symbol": symbol.upper(),
            "resolution": "D",
            "from": int(start.timestamp()),
            "to": int(end.timestamp()),
            "token": api_key,
        },
        timeout=15,
    )
    res.raise_for_status()
    payload = res.json()
    if payload.get("s") != "ok" or not payload.get("t"):
        logger.info("Finnhub (dev) returned no data for %s: status=%s", symbol, payload.get("s"))
        return None
    df = pd.DataFrame({
        "Open": payload["o"], "High": payload["h"], "Low": payload["l"],
        "Close": payload["c"], "Volume": payload["v"],
    }, index=pd.to_datetime(payload["t"], unit="s"))
    return df


def _fetch_marketstack_dev(symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    """DEV/TEST ONLY -- see module docstring. Marketstack's free plan: EOD
    daily bars via /v1/eod, 100 requests/MONTH (no published per-minute
    cap), and its own pricing page confirms "Commercial Use" is a paid-
    tier-only feature not included on the Free plan."""
    _dev_guard()
    api_key = os.getenv("MARKETSTACK_API_KEY")
    if not api_key:
        return None
    days = _PERIOD_DAYS.get(period, 182)
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    res = get_with_backoff(
        MARKETSTACK_EOD_URL,
        params={
            "access_key": api_key,
            "symbols": symbol.upper(),
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "limit": 1000,
        },
        timeout=15,
    )
    res.raise_for_status()
    payload = res.json()
    data = payload.get("data") or []
    if not data:
        logger.info("Marketstack (dev) returned no data for %s: %s", symbol, payload.get("error"))
        return None
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").rename(
        columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    )
    df = df.astype({"Open": float, "High": float, "Low": float, "Close": float, "Volume": float})
    return df.sort_index()[["Open", "High", "Low", "Close", "Volume"]]


def _fetch_baostock_dev(symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    """DEV/TEST ONLY -- see module docstring. BaoStock: free, no
    registration/API key, China A-share daily history via a stateful
    login/query/logout session against BaoStock's own data server (NOT a
    parameterized HTTP GET like the other four fetch functions above).
    Fills a real gap -- services/market_data_gateway.py has zero A-share
    coverage today. Commercial-use terms for the underlying DATA are
    unconfirmed (module docstring); the wrapper library's BSD license only
    covers the client code.

    Symbol format is BaoStock's own convention, NOT the ".SH"/".SZ" suffix
    style used elsewhere in this codebase: lowercase exchange prefix +
    dot + code, e.g. "sh.600000" (Shanghai) / "sz.000001" (Shenzhen).
    Caller is responsible for passing that format -- no normalization
    layer here, this is a harness, not the production ticker resolver."""
    _dev_guard()
    try:
        import baostock as bs
    except ImportError:
        logger.info("baostock (dev) package not installed -- skipping")
        return None

    days = _PERIOD_DAYS.get(period, 182)
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)

    lg = bs.login()
    if lg.error_code != "0":
        logger.info("BaoStock (dev) login failed: %s", lg.error_msg)
        return None
    try:
        rs = bs.query_history_k_data_plus(
            symbol,
            "date,open,high,low,close,volume",
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            frequency="d",
            adjustflag="2",
        )
        if rs.error_code != "0":
            logger.info("BaoStock (dev) query failed for %s: %s", symbol, rs.error_msg)
            return None
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            logger.info("BaoStock (dev) returned no rows for %s", symbol)
            return None
        df = pd.DataFrame(rows, columns=rs.fields)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").rename(
            columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
        )
        df = df.astype({"Open": float, "High": float, "Low": float, "Close": float, "Volume": float})
        return df.sort_index()[["Open", "High", "Low", "Close", "Volume"]]
    finally:
        bs.logout()


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
    # BaoStock uses its own "sh.600000"/"sz.000001" symbol convention, not
    # the US-ticker-style test_symbol above -- kept as a separate env var
    # rather than forcing one shared symbol format across all 6 providers.
    test_symbol_baostock = os.getenv("DEV_ROTATION_TEST_SYMBOL_BAOSTOCK", "sh.600000")

    rotator = DevProviderRotator({
        "alpaca": lambda: _fetch_alpaca_dev(test_symbol),
        "polygon": lambda: _fetch_polygon_dev(test_symbol),
        "twelvedata": lambda: _fetch_twelvedata_dev(test_symbol),
        "finnhub": lambda: _fetch_finnhub_dev(test_symbol),
        "marketstack": lambda: _fetch_marketstack_dev(test_symbol),
        "baostock": lambda: _fetch_baostock_dev(test_symbol_baostock),
    })

    for i in range(6):
        provider, df = rotator.fetch()
        rows = 0 if df is None else len(df)
        print(f"call {i}: served by {provider} -> {rows} rows")
