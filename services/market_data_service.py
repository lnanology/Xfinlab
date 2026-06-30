import yfinance as yf
from typing import Dict


class MarketDataService:
    """Service to fetch market data using yfinance"""

    def get_stock_data(self, symbol: str) -> Dict:
        """
        Get stock data for a given symbol
        """

        try:

            ticker = yf.Ticker(symbol)

            info = ticker.info

            # Price
            price = info.get("currentPrice") or info.get(
                "regularMarketPrice", 0
            )

            # Volume ratio
            volume = info.get("volume", 0)
            avg_volume = info.get("averageVolume", 1)

            volume_ratio = (
                round(volume / avg_volume, 2)
                if avg_volume > 0
                else 0
            )

            # Trend
            ma50 = info.get("fiftyDayAverage", price)

            trend = (
                "bullish"
                if price and ma50 and price > ma50
                else "bearish"
            )

            # Breakout
            week_high = info.get("fiftyTwoWeekHigh", price)

            breakout = bool(
                price and week_high and price >= (week_high * 0.95)
            )

            # Sentiment
            recommendation = (
                info.get("recommendationKey", "hold")
                .lower()
            )

            sentiment = (
                "bullish"
                if recommendation in ["buy", "strong_buy"]
                else "bearish"
            )

            return {
                "symbol": symbol.upper(),
                "price": round(price, 2) if price else 0,
                "volume": volume,
                "avg_volume": avg_volume,
                "volume_ratio": volume_ratio,
                "market_cap": info.get("marketCap"),
                "trend": trend,
                "breakout": breakout,
                "sentiment": sentiment,
            }

        except Exception as e:

            return {
                "symbol": symbol.upper(),
                "error": str(e)
            }


# 建立全域 Service
market_service = MarketDataService()


# 提供給 API 使用
def get_stock_data(symbol: str):
    return market_service.get_stock_data(symbol)


if __name__ == "__main__":

    print(
        get_stock_data("AAPL")
    )