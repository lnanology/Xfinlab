"""
Binance Exchange Market Data Service -- 2026-08-26, Data Factory Step 7
(AJ: "繼續加多啲data source" after the Ownership/Control Score arc
wrapped up).

What this is, and why it's different from services/crypto_service.py:
that module hits CoinGecko, which aggregates/averages price across many
exchanges -- a legitimate "what's the market price" number, but it
can never answer "how much is actually trading on one specific real
exchange right now" (24h volume, real price-change momentum on that
venue). Binance is the largest crypto spot exchange by volume; its own
24hr ticker stats are a genuinely different data type (single-exchange
real activity) from CoinGecko's cross-exchange average, not a
duplicate of what this codebase already has.

Data source: Binance's public REST API, market-data-only endpoints, no
API key required. Critically NOT api.binance.com -- confirmed via
research that domain returns HTTP 451 ("Unavailable For Legal Reasons")
for US-origin IP addresses since Binance stopped serving US persons on
its main platform, and Railway (where this app runs) is very likely
US-hosted. Binance itself publishes data-api.binance.vision specifically
as a market-data-only mirror NOT subject to that geo-block, for exactly
this use case (public data consumers who aren't trading) -- that's the
base URL used here. Same public, free, well-documented, and (per
Binance's own market-data-only FAQ) has generous rate limits for GET
market data.

Scope: the same 10 tickers services/crypto_service.py already covers
(BTC/ETH/SOL/BNB/XRP/ADA/DOGE/DOT/AVAX/LINK), each as its {TICKER}USDT
spot pair -- keeps this consistent with what the rest of the site
already treats as "the crypto universe" rather than introducing a
different curated list.
"""
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional

from services.outbound_http import get_with_backoff
from services.data_source_registry import (
    register_source, is_source_enabled, record_run_start,
    record_run_success, record_run_error,
)

logger = logging.getLogger(__name__)

SOURCE_KEY = "binance_exchange"
register_source(SOURCE_KEY, "Binance Exchange Market Data", "crypto")

# NOT api.binance.com -- see module docstring on the US-IP 451 block.
BASE_URL = "https://data-api.binance.vision/api/v3"
ATTRIBUTION = "Data sourced from Binance's public market-data API (data-api.binance.vision). Not investment advice."

# Ticker -> Binance spot symbol. Kept 1:1 with services/crypto_service.py's
# CRYPTO_MAP tickers so both modules describe "the same 10 coins", just
# from different data sources (cross-exchange average vs one real venue).
_SYMBOLS = {
    "BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "BNB": "BNBUSDT",
    "XRP": "XRPUSDT", "ADA": "ADAUSDT", "DOGE": "DOGEUSDT", "DOT": "DOTUSDT",
    "AVAX": "AVAXUSDT", "LINK": "LINKUSDT",
}

_CACHE_TTL_SECONDS = 5 * 60  # crypto moves fast -- much shorter TTL than the macro/positioning collectors
_cache: Dict[str, Dict] = {}  # ticker -> {"fetched_at": epoch, "row": {...}}

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _get_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_exchange_ticker (
            ticker TEXT NOT NULL,
            exchange TEXT NOT NULL DEFAULT 'binance',
            last_price REAL,
            price_change_pct_24h REAL,
            high_24h REAL,
            low_24h REAL,
            volume_24h REAL,
            quote_volume_24h REAL,
            fetched_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (ticker, exchange)
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def _to_float(raw) -> Optional[float]:
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _persist_row(ticker: str, row: dict):
    try:
        conn = _get_db()
        conn.execute(
            """
            INSERT INTO crypto_exchange_ticker
                (ticker, exchange, last_price, price_change_pct_24h, high_24h, low_24h, volume_24h, quote_volume_24h, fetched_at)
            VALUES (?, 'binance', ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(ticker, exchange) DO UPDATE SET
                last_price=excluded.last_price, price_change_pct_24h=excluded.price_change_pct_24h,
                high_24h=excluded.high_24h, low_24h=excluded.low_24h,
                volume_24h=excluded.volume_24h, quote_volume_24h=excluded.quote_volume_24h,
                fetched_at=datetime('now')
            """,
            (ticker, row["last_price"], row["price_change_pct_24h"], row["high_24h"],
             row["low_24h"], row["volume_24h"], row["quote_volume_24h"]),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("crypto_exchange_service: failed to persist %s: %s", ticker, e)


def _load_persisted(ticker: str) -> Optional[dict]:
    try:
        conn = _get_db()
        r = conn.execute(
            "SELECT * FROM crypto_exchange_ticker WHERE ticker=? AND exchange='binance'", (ticker,)
        ).fetchone()
        conn.close()
        return dict(r) if r else None
    except Exception:
        return None


def get_ticker(ticker: str) -> Optional[Dict]:
    """
    Returns:
        {"ticker": "BTC", "binance_symbol": "BTCUSDT", "last_price": 64213.5,
         "price_change_pct_24h": 2.31, "high_24h": ..., "low_24h": ...,
         "volume_24h": ..., "quote_volume_24h": ..., "attribution": "..."}
        None if this ticker isn't in the tracked list, or if live fetch,
        cache, AND persisted DB all have nothing (e.g. very first run).
    """
    ticker = (ticker or "").upper().strip()
    symbol = _SYMBOLS.get(ticker)
    if not symbol:
        return None

    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(ticker)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["row"]

    if not is_source_enabled(SOURCE_KEY):
        persisted = _load_persisted(ticker)
        return (cached["row"] if cached else None) or persisted

    record_run_start(SOURCE_KEY)
    try:
        res = get_with_backoff(f"{BASE_URL}/ticker/24hr", params={"symbol": symbol}, timeout=10)
        if res.status_code != 200:
            record_run_error(SOURCE_KEY, f"{symbol}: HTTP {res.status_code}")
            persisted = _load_persisted(ticker)
            return (cached["row"] if cached else None) or persisted
        raw = res.json()
    except Exception as e:
        record_run_error(SOURCE_KEY, f"{symbol}: {e}")
        persisted = _load_persisted(ticker)
        return (cached["row"] if cached else None) or persisted

    row = {
        "ticker": ticker,
        "binance_symbol": symbol,
        "last_price": _to_float(raw.get("lastPrice")),
        "price_change_pct_24h": _to_float(raw.get("priceChangePercent")),
        "high_24h": _to_float(raw.get("highPrice")),
        "low_24h": _to_float(raw.get("lowPrice")),
        "volume_24h": _to_float(raw.get("volume")),
        "quote_volume_24h": _to_float(raw.get("quoteVolume")),
        "attribution": ATTRIBUTION,
    }
    if row["last_price"] is None:
        record_run_error(SOURCE_KEY, f"{symbol}: response missing lastPrice")
        persisted = _load_persisted(ticker)
        return (cached["row"] if cached else None) or persisted

    _cache[ticker] = {"fetched_at": now, "row": row}
    _persist_row(ticker, row)
    record_run_success(SOURCE_KEY)
    return row


def get_all_tickers() -> Dict[str, Optional[dict]]:
    return {ticker: get_ticker(ticker) for ticker in _SYMBOLS}


if __name__ == "__main__":
    import json
    print(json.dumps(get_all_tickers(), indent=2))
