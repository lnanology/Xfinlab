
class AnalystAgent:
    @staticmethod
    def analyze(market_data):
        """
        2026-07-18 fix: this used to compare the current price against a
        LITERAL hardcoded threshold of 100 (`price > 100`) -- meaning any
        stock trading above $100 was unconditionally "UP" and anything
        below was "DOWN", regardless of what the price actually did. A
        $50 stock up 20% today showed "DOWN"; a $500 stock that crashed
        30% showed "UP". Fixed to use the real trend_direction already
        computed by the Confluence Engine (api/pipeline_api.py passes it
        through in market_data) when available, falling back to real
        price-series comparison (today's price vs the start of the
        fetched price window) rather than an arbitrary constant.
        """
        trend_direction = market_data.get("trend_direction")
        if trend_direction == "偏多":
            return {"trend": "UP", "confidence": 0.7}
        if trend_direction == "偏空":
            return {"trend": "DOWN", "confidence": 0.7}

        prices = market_data.get("prices") or []
        if len(prices) >= 2 and prices[0]:
            return {"trend": "UP" if prices[-1] > prices[0] else "DOWN", "confidence": 0.6}

        return {"trend": "UNKNOWN", "confidence": 0.3}
