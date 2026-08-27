"""
Coinbase Exchange Market Data Service -- 2026-08-27, Data Factory
Step 8c (AJ: "一次過全加可以嗎" -- add EIA + Treasury + Coinbase together
after Binance shipped clean on the first try).

Same rationale as services/crypto_exchange_service.py (Binance, Data
Factory Step 7): services/crypto_service.py's CoinGecko numbers are a
cross-exchange AVERAGE price, not "what's actually trading on one real
venue right now." Binance and Coinbase are two of the largest spot
exchanges by volume; having both means a caller (or a future feature)
can compare a single coin's price/volume across two real venues instead
of trusting one exchange's numbers as if they were the whole market --
e.g. spotting a meaningful price gap between them, which a
single-exchange or an averaged feed can't show at all.

Source: Coinbase's Exchange REST API (api.exchange.coinbase.com),
GET /products/{product_id}/stats -- confirmed via Coinbase's own
developer docs (docs.cdp.coinbase.com/api-reference/exchange-api/
rest-api/products/get-product-stats) to require NO authentication
(`security: []` in Coinbase's own OpenAPI spec for this specific
endpoint -- auth is only required for order placement/account
endpoints elsewhere in the same API). No US-IP geo-block risk like
Binance's api.binance.com -- Coinbase is a US-headquartered, US-licensed
exchange; its market-data endpoints are not blocked for US traffic
(unlike Binance's main domain, which blocks the US specifically because
Binance itself doesn't serve US persons there).

Response shape (confirmed from Coinbase's own OpenAPI example): open,
high, low, last, volume, volume_30day -- all as STRINGS, and `volume` is
in BASE currency units (not quote/USD). There is no ready-made 24h
"price change %" or "quote volume" field the way Binance's ticker
gives -- this module derives:
  - price_change_pct_24h = (last - open) / open * 100 (open here IS the
    24h-ago open per Coinbase's own stats semantics)
  - quote_volume_24h_usd_est = volume * last -- an ESTIMATE (last price
    applied across the whole 24h volume, not each trade's actual price),
    explicitly flagged via `quote_volume_is_estimated: True` so no
    caller mistakes it for an exact figure the way Binance's genuine
    quoteVolume field is.

Scope: same 10 tickers as crypto_service.py / crypto_exchange_service.py,
each as its {TICKER}-USD Coinbase product ID.
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

SOURCE_KEY = "coinbase_exchange"
register_source(SOURCE_KEY, "Coinbase Exchange Market Data", "crypto")

BASE_URL = "https://api.exchange.coinbase.com"
ATTRIBUTION = "Data sourced from Coinbase's public Exchange API (api.exchange.coinbase.com). Not investment advice."

# Same 10 tickers as crypto_service.py's CRYPTO_MAP / crypto_exchange_
# service.py's _SYMBOLS -- kept 1:1 so all three modules describe "the
# same 10 coins" from three different vantage points (aggregate,
# Binance, Coinbase).
_PRODUCTS = {
    "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD", "BNB": "BNB-USD",
    "XRP": "XRP-USD", "ADA": "ADA-USD", "DOGE": "DOGE-USD", "DOT": "DOT-USD",
    "AVAX": "AVAX-USD", "LINK": "LINK-USD",
}

_CACHE_TTL_SECONDS = 5 * 60  # same short TTL as the Binance collector -- crypto moves fast
_cache: Dict[str, Dict] = {}  # ticker -> {"fetched_at": epoch, "row": {...}}

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _get_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS coinbase_exchange_ticker (
            ticker TEXT NOT NULL,
            exchange TEXT NOT NULL DEFAULT 'coinbase',
            last_price REAL,
            price_change_pct_24h REAL,
            high_24h REAL,
            low_24h REAL,
            volume_24h REAL,
            quote_volume_24h_usd_est REAL,
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
            INSERT INTO coinbase_exchange_ticker
                (ticker, exchange, last_price, price_change_pct_24h, high_24h, low_24h, volume_24h, quote_volume_24h_usd_est, fetched_at)
            VALUES (?, 'coinbase', ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(ticker, exchange) DO UPDATE SET
                last_price=excluded.last_price, price_change_pct_24h=excluded.price_change_pct_24h,
                high_24h=excluded.high_24h, low_24h=excluded.low_24h,
                volume_24h=excluded.volume_24h, quote_volume_24h_usd_est=excluded.quote_volume_24h_usd_est,
                fetched_at=datetime('now')
            """,
            (ticker, row["last_price"], row["price_change_pct_24h"], row["high_24h"],
             row["low_24h"], row["volume_24h"], row["quote_volume_24h_usd_est"]),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.info("coinbase_exchange_service: failed to persist %s: %s", ticker, e)


def _load_persisted(ticker: str) -> Optional[dict]:
    try:
        conn = _get_db()
        r = conn.execute(
            "SELECT * FROM coinbase_exchange_ticker WHERE ticker=? AND exchange='coinbase'", (ticker,)
        ).fetchone()
        conn.close()
        return dict(r) if r else None
    except Exception:
        return None


def get_ticker(ticker: str) -> Optional[Dict]:
    """
    Returns:
        {"ticker": "BTC", "coinbase_product_id": "BTC-USD", "last_price": 64213.5,
         "price_change_pct_24h": 2.31, "high_24h": ..., "low_24h": ...,
         "volume_24h": ..., "quote_volume_24h_usd_est": ...,
         "quote_volume_is_estimated": True, "attribution": "..."}
        None if this ticker isn't tracked, or if live fetch, cache, AND
        persisted DB all have nothing.
    """
    ticker = (ticker or "").upper().strip()
    product_id = _PRODUCTS.get(ticker)
    if not product_id:
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
        res = get_with_backoff(f"{BASE_URL}/products/{product_id}/stats", timeout=10)
        if res.status_code != 200:
            record_run_error(SOURCE_KEY, f"{product_id}: HTTP {res.status_code}")
            persisted = _load_persisted(ticker)
            return (cached["row"] if cached else None) or persisted
        raw = res.json()
    except Exception as e:
        record_run_error(SOURCE_KEY, f"{product_id}: {e}")
        persisted = _load_persisted(ticker)
        return (cached["row"] if cached else None) or persisted

    last_price = _to_float(raw.get("last"))
    open_price = _to_float(raw.get("open"))
    volume = _to_float(raw.get("volume"))

    if last_price is None:
        record_run_error(SOURCE_KEY, f"{product_id}: response missing last price")
        persisted = _load_persisted(ticker)
        return (cached["row"] if cached else None) or persisted

    price_change_pct_24h = None
    if open_price:
        price_change_pct_24h = round((last_price - open_price) / open_price * 100, 3)

    row = {
        "ticker": ticker,
        "coinbase_product_id": product_id,
        "last_price": last_price,
        "price_change_pct_24h": price_change_pct_24h,
        "high_24h": _to_float(raw.get("high")),
        "low_24h": _to_float(raw.get("low")),
        "volume_24h": volume,
        "quote_volume_24h_usd_est": round(volume * last_price, 2) if volume is not None else None,
        "quote_volume_is_estimated": True,  # see module docstring -- not a real per-trade quote volume
        "attribution": ATTRIBUTION,
    }

    _cache[ticker] = {"fetched_at": now, "row": row}
    _persist_row(ticker, row)
    record_run_success(SOURCE_KEY)
    return row


def get_all_tickers() -> Dict[str, Optional[dict]]:
    return {ticker: get_ticker(ticker) for ticker in _PRODUCTS}


if __name__ == "__main__":
    import json
    print(json.dumps(get_all_tickers(), indent=2))
