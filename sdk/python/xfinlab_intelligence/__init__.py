"""XFINLAB Intelligence API -- official Python client.

Wraps https://api.xfinlab.com's Intelligence API v1 (see api/intelligence.py
in the main XFINLAB repo for the server-side implementation this mirrors).
Deliberately thin: one class, one dependency (`requests`), no internal
imports -- every method is a direct 1:1 wrapper around a real endpoint,
returning the same `data` payload the API's {"success","data","meta","error"}
envelope already carries. No client-side caching, retries, or "smart"
behavior that could silently mask a real API error.

Not yet published to PyPI -- there are no paying developers on this API
yet to justify the ongoing maintenance of a public package release (same
honesty-over-premature-infrastructure posture as the rest of this
codebase). Until then, install straight from the repo:

    pip install "git+https://github.com/lnanology/Xfinlab.git#subdirectory=sdk/python"

or just copy this one file into your own project -- it has zero internal
imports, so vendoring it works too.

Get a free API key (issued instantly): https://www.xfinlab.com/intelligence-api.html
"""
from __future__ import annotations

from typing import Optional

import requests

__version__ = "0.1.0"
__all__ = ["XfinlabClient", "XfinlabError"]


class XfinlabError(Exception):
    """Raised for any non-2xx HTTP response or an explicit
    {"success": false} envelope. `status_code` is None only if the request
    never got a response at all (network error) -- requests' own exception
    propagates unchanged in that case, this class is not used for it."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class XfinlabClient:
    """
    Example:
        from xfinlab_intelligence import XfinlabClient

        client = XfinlabClient(api_key="xfl_...")
        events = client.events(ticker="AAPL", limit=10)
        sentiment = client.sentiment("AAPL")
        technical = client.technical("AAPL", period="6mo")
        stress = client.stress_test("AAPL", amount=10000, horizon_days=252)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.xfinlab.com/api",
        timeout: int = 30,
    ):
        if not api_key:
            raise ValueError(
                "api_key is required -- get a free key at "
                "https://www.xfinlab.com/intelligence-api.html"
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    # -- internals -----------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ):
        url = f"{self.base_url}{path}"
        headers = {"X-API-Key": self.api_key}
        # Drop None-valued query params rather than sending them literally
        # (e.g. "ticker=None") -- lets every wrapper method below pass
        # Optional[...] args straight through unconditionally.
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}

        resp = self._session.request(
            method,
            url,
            headers=headers,
            params=clean_params or None,
            json=json_body,
            timeout=self.timeout,
        )
        try:
            body = resp.json()
        except ValueError:
            raise XfinlabError(
                f"Non-JSON response ({resp.status_code}): {resp.text[:200]!r}",
                resp.status_code,
            )

        if not resp.ok:
            detail = (body or {}).get("detail") or (body or {}).get("error")
            raise XfinlabError(detail or f"Request failed ({resp.status_code})", resp.status_code)

        if isinstance(body, dict) and body.get("success") is False:
            raise XfinlabError(body.get("error") or "Request failed", resp.status_code)

        if isinstance(body, dict) and "data" in body:
            return body["data"]
        return body

    def _get(self, path: str, params: Optional[dict] = None):
        return self._request("GET", path, params=params)

    def _post(self, path: str, json_body: Optional[dict] = None):
        return self._request("POST", path, json_body=json_body)

    # -- public, unauthenticated ----------------------------------------------

    def status(self) -> dict:
        """No API key needed -- lets you check what's live before signing up."""
        return self._get("/intelligence/status")

    # -- v1 endpoints (require an API key) ------------------------------------

    def events(self, ticker: Optional[str] = None, limit: int = 20) -> list:
        return self._get("/intelligence/v1/events", params={"ticker": ticker, "limit": limit})

    def sentiment(self, ticker: str, limit: int = 10) -> dict:
        return self._get("/intelligence/v1/sentiment", params={"ticker": ticker, "limit": limit})

    def debate(self, ticker: str) -> dict:
        """The most expensive endpoint (4 sequential LLM calls server-side,
        weighted 5x in your daily quota) -- see intelligence-api.html for
        the full cost-weighting table."""
        return self._get("/intelligence/v1/debate", params={"ticker": ticker})

    def intel_latest(self, limit: int = 5, lang: str = "zh-HK") -> list:
        return self._get(
            "/intelligence/v1/intel/latest", params={"limit": limit, "lang": lang}
        )

    def intel_for_ticker(self, ticker: str, limit: int = 5, lang: str = "zh-HK") -> list:
        return self._get(
            f"/intelligence/v1/intel/{ticker}", params={"limit": limit, "lang": lang}
        )

    def technical(
        self, ticker: str, period: str = "6mo", interval: str = "1d", lang: str = "en"
    ) -> dict:
        return self._get(
            f"/intelligence/v1/technical/{ticker}",
            params={"period": period, "interval": interval, "lang": lang},
        )

    def stress_test(
        self,
        symbol: str,
        amount: float,
        horizon_days: int = 252,
        n_simulations: Optional[int] = None,
        lang: Optional[str] = None,
    ) -> dict:
        body = {"symbol": symbol, "amount": amount, "horizon_days": horizon_days}
        if n_simulations is not None:
            body["n_simulations"] = n_simulations
        if lang is not None:
            body["lang"] = lang
        return self._post("/intelligence/v1/stress-test", json_body=body)
