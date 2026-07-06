
import numpy as np

class FeatureEngine:
    @staticmethod
    def build(market_data):
        price = market_data.get("price", 100)
        volume = market_data.get("volume", 1)
        return {
            "momentum": price * 0.01,
            "volume_pressure": volume / 1000,
            "volatility": float(abs(np.random.randn()) * 10)
        }
