"""
XFINLAB News Service Test
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.news_service import NewsService


def test_news(symbol: str):
    print(f"\n{'=' * 50}")
    print(f"  News for {symbol}")
    print("=" * 50)

    service = NewsService()
    articles = service.get_company_news(symbol)

    if not articles:
        print("  No news found.")
        return

    for i, article in enumerate(articles[:5], 1):
        print(f"\n  [{i}] {article['title']}")
        print(f"      Source      : {article['source']}")
        print(f"      Published   : {article['published_at']}")


if __name__ == "__main__":
    symbols = ["AAPL", "NVDA", "TSLA", "MSFT", "META"]
    for symbol in symbols:
        test_news(symbol)
