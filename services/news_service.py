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

    def get_company_news(
        self,
        symbol: str,
        from_date: str = None,
        to_date: str = None,
        page_size: int = 10,
    ) -> List[Dict[str, str]]:
        """
        Fetch news for a given stock symbol, optionally scoped to a date
        window (NewsAPI's /v2/everything supports `from`/`to` as ISO
        date strings, e.g. "2026-07-10") -- added so callers like
        services/anomaly_history_service.py can ask "what news ran
        around the date of this volume spike" instead of only ever
        getting today's latest headlines.

        Args:
            symbol (str): Stock symbol e.g. 'AAPL', 'NVDA', or a
                suffixed global ticker like '2330.TW' (the exchange
                suffix is stripped before building the search query --
                NewsAPI has no idea what ".TW" means).
            from_date / to_date (str): optional ISO date strings
                ("YYYY-MM-DD") bounding the search window. Omit both for
                the original "latest news" behaviour.
            page_size (int): max articles to return (NewsAPI cap: 100).

        Returns:
            List[Dict]: articles with title, source, published_at, url
        """
        symbol = symbol.upper()
        bare_symbol = symbol.split(".")[0]
        company = SYMBOL_MAP.get(symbol, SYMBOL_MAP.get(bare_symbol, bare_symbol))

        params = {
            "q": f'"{company}" stock OR "{bare_symbol}" stock',
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": page_size,
            "apiKey": self.api_key,
        }
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

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
                        "url": article.get("url", ""),
                    }
                )

            return results

        except requests.exceptions.RequestException as e:
            print(f"[NewsService] Error fetching news for {symbol}: {e}")
            return []
