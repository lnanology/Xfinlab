"""
Shared outbound HTTP helper -- honest User-Agent + 429/503 backoff for
requests THIS app makes TO third-party APIs (NewsAPI, CoinGecko, etc).

Not to be confused with the SlowAPI-based limiter in backend/main.py,
which rate-limits INBOUND requests from XFINLAB's own users -- this
module is about being a good citizen towards the external services
XFINLAB depends on, per the data-collection compliance guidance:
identify yourself honestly, don't hammer a server, and back off instead
of retrying immediately when a server says 429/503.

Usage: replace a bare `requests.get(url, params=params, timeout=10)` with
`get_with_backoff(url, params=params, timeout=10)`. Same return value
(a requests.Response, or raises the same exceptions requests.get would),
so this is a drop-in change at every call site.
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "XFINLABBot/1.0 (+https://www.xfinlab.com; contact: support@xfinlab.com)"
DEFAULT_BACKOFF_SECONDS = 30
DEFAULT_MAX_RETRIES = 1  # one retry after one backoff -- enough to ride out a brief rate-limit window without turning a single request into a long retry storm


def get_with_backoff(
    url: str,
    params: dict = None,
    headers: dict = None,
    timeout: float = 10,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
) -> requests.Response:
    """
    requests.get() wrapper that (1) always sends an honest, identifying
    User-Agent (merged with any caller-supplied headers, caller's values
    win on conflict) and (2) backs off and retries once (by default) on
    HTTP 429/503 instead of either hammering again immediately or letting
    the caller's own except-block silently swallow a rate-limit response
    as if it were just "no data".
    """
    merged_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        merged_headers.update(headers)

    attempt = 0
    while True:
        response = requests.get(url, params=params, headers=merged_headers, timeout=timeout)
        if response.status_code in (429, 503) and attempt < max_retries:
            attempt += 1
            logger.info(
                "outbound_http: %s returned HTTP %s, backing off %ss then retrying (attempt %s/%s)",
                url, response.status_code, backoff_seconds, attempt, max_retries,
            )
            time.sleep(backoff_seconds)
            continue
        return response
