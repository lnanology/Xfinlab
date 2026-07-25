import time
import yfinance as yf
from typing import Dict


class MarketDataService:
    """Service to fetch market data using yfinance"""

    def get_stock_data(self, symbol: str, retries: int = 3) -> Dict:
        """
        Get stock data for a given symbol.

        Yahoo Finance's edge network occasionally returns an SSL certificate
        for the wrong hostname (fc.yahoo.com) - this is intermittent and
        usually resolves on retry, so we retry a few times with a short
        delay before giving up.
        """

        last_error = None

        for attempt in range(retries):
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
                # 2026-07-25 fix: indices/ETFs/other symbols with no analyst
                # coverage (e.g. ^GSPC, ^HSI, ^VIX, bond-yield tickers) come
                # back from yfinance with "recommendationKey" PRESENT but set
                # to None, not absent -- so `.get("recommendationKey",
                # "hold")` returned None (the default only applies when the
                # key is missing entirely), and `.lower()` on None raised
                # AttributeError. That got caught by this function's own
                # retry loop, but silently burned all 3 retries (with a 1s
                # sleep between each) on every single request for these
                # symbols before finally giving up and returning an "error"
                # dict -- adding several seconds of pure waste to an already
                # slow multi-service /api/ai-analysis call, and a real risk
                # of that endpoint's overall response time tipping past a
                # proxy/browser timeout ("Analysis failed, please try again
                # later") purely because of this one field.
                recommendation = (info.get("recommendationKey") or "hold").lower()

                sentiment = (
                    "bullish"
                    if recommendation in ["buy", "strong_buy"]
                    else "bearish"
                )

                # Price change % vs previous close - real figure (not
                # estimated), used by AnomalyEngine for price_spike
                # detection. yfinance sometimes exposes this directly as
                # regularMarketChangePercent; fall back to computing it
                # from previousClose if that field is missing.
                previous_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
                change_pct = info.get("regularMarketChangePercent")
                if change_pct is None and previous_close and price:
                    change_pct = ((price - previous_close) / previous_close) * 100
                price_change_pct = round(change_pct, 2) if change_pct is not None else 0.0

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
                    "price_change_pct": price_change_pct,
                }

            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    time.sleep(1)
                continue

        return {
            "symbol": symbol.upper(),
            "error": str(last_error)
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
