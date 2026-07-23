
import time
import random

class MarketStream:
    @staticmethod
    def live(ticker):
        price = 100
        while True:
            price += random.uniform(-2, 2)
            yield {"ticker": ticker, "price": round(price, 2), "volume": random.randint(1000,5000), "timestamp": time.time()}
