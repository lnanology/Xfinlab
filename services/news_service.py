"""
XFINLAB Event Intelligence V1
News Service - Fetches company news from NewsAPI
"""

import os
import requests
from typing import List, Dict
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Symbol to company name mapping
SYMBOL_MAP = {
    "AAPL": "Apple",
    "NVDA": "NVIDIA",
    "TSLA": "Tesla",
    "MSFT": "Microsoft",
    "META": "Meta",
}


class NewsService:
    """Fetches latest company news from NewsAPI"""

    BASE_URL = "https://newsapi.org/v2/everything"

    def __init__(self):
        self.api_key = os.getenv("NEWS_API_KEY")
        if not self.api_key:
            raise ValueError("NEWS_API_KEY not found in .env file")

    def get_company_news(self, symbol: str) -> List[Dict[str, str]]:
        """
        Fetch latest news for a given stock symbol

        Args:
            symbol (str): Stock symbol e.g. 'AAPL', 'NVDA'

        Returns:
            List[Dict]: List of news articles with title, source, published_at
        """
        symbol = symbol.upper()
        company = SYMBOL_MAP.get(symbol, symbol)

        params = {
            "q": f'"{company}" stock OR "{symbol}" stock',
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 10,
            "apiKey": self.api_key,
        }

        try:
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            articles = data.get("articles", [])
            results = []

            for article in articles:
                results.append(
                    {
                        "title": article.get("title", ""),
                        "source": article.get("source", {}).get("name", ""),
                        "published_at": article.get("publishedAt", ""),
                    }
                )

            return results

        except requests.exceptions.RequestException as e:
            print(f"[NewsService] Error fetching news for {symbol}: {e}")
            return []
