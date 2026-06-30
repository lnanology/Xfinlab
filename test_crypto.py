"""
XFINLAB Crypto Service Test
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.crypto_service import CryptoService


def test_crypto(symbol: str):
    print(f"\n{'=' * 50}")
    service = CryptoService()
    result = service.get_crypto_data(symbol)

    if not result:
        print(f"  [{symbol}] No data found.")
        return

    print(f"  Symbol      : {result['symbol']}")
    print(f"  Price       : ${result['price']:,.2f}")
    print(f"  Market Cap  : ${result['market_cap']:,.0f}")
    print(f"  Volume 24H  : ${result['volume_24h']:,.0f}")
    print("=" * 50)


if __name__ == "__main__":
    coins = ["bitcoin", "ethereum", "solana"]
    for coin in coins:
        test_crypto(coin)
