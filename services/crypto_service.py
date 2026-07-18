"""
XFINLAB Event Intelligence V1
Crypto Service - Fetches cryptocurrency data from CoinGecko API (no API key required)
"""

import requests
from typing import Dict, Optional

from services.outbound_http import get_with_backoff


# CoinGecko ID to symbol mapping
CRYPTO_MAP = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "binancecoin": "BNB",
    "ripple": "XRP",
    "cardano": "ADA",
    "dogecoin": "DOGE",
    "polkadot": "DOT",
    "avalanche-2": "AVAX",
    "chainlink": "LINK",
}

# Reverse map: symbol → coingecko id
SYMBOL_TO_ID = {v: k for k, v in CRYPTO_MAP.items()}


class CryptoService:
    """Fetches live cryptocurrency data from CoinGecko API"""

    BASE_URL = "https://api.coingecko.com/api/v3"

    def get_crypto_data(self, symbol: str) -> Optional[Dict]:
        """
        Fetch current crypto market data

        Args:
            symbol (str): CoinGecko coin ID (e.g. 'bitcoin', 'ethereum', 'solana')
                          or ticker symbol (e.g. 'BTC', 'ETH', 'SOL')

        Returns:
            Dict: Crypto market data with symbol, price, market_cap, volume_24h
        """
        # Resolve input to CoinGecko ID
        input_clean = symbol.lower().strip()

        if input_clean in CRYPTO_MAP:
            coin_id = input_clean
            ticker = CRYPTO_MAP[coin_id]
        elif input_clean.upper() in SYMBOL_TO_ID:
            coin_id = SYMBOL_TO_ID[input_clean.upper()]
            ticker = input_clean.upper()
        else:
            coin_id = input_clean
            ticker = input_clean.upper()

        url = f"{self.BASE_URL}/coins/{coin_id}"
        params = {
            "localization": "false",
            "tickers": "false",
            "community_data": "false",
            "developer_data": "false",
        }

        try:
            # 2026-07-18 compliance fix: honest User-Agent + 429/503
            # backoff instead of a bare requests.get() (see
            # services/outbound_http.py). CoinGecko's free tier is rate-
            # limited and does return 429s under load.
            response = get_with_backoff(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            market = data.get("market_data", {})

            return {
                "symbol": ticker,
                "price": market.get("current_price", {}).get("usd", 0),
                "market_cap": market.get("market_cap", {}).get("usd", 0),
                "volume_24h": market.get("total_volume", {}).get("usd", 0),
            }

        except requests.exceptions.HTTPError as e:
            print(f"[CryptoService] Coin '{symbol}' not found or API error: {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[CryptoService] Network error: {e}")
            return None
