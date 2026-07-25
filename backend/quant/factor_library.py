
import numpy as np

class FactorLibrary:
    @staticmethod
    def momentum(prices):
        # 2026-07-25 fix: a zero/near-zero first price (bad data point, or
        # a defaulted-but-still-zero fallback series) divides to inf/NaN,
        # which -- same as tensor_network.py's corrcoef fix above -- ends up
        # crashing the whole /api/pipeline response at JSON-encoding time.
        if not prices[0]:
            return 0.0
        return (prices[-1] - prices[0]) / prices[0]
    @staticmethod
    def volatility(returns):
        return float(np.std(returns))
    @staticmethod
    def mean_reversion(prices):
        return float(np.mean(prices) - prices[-1])
    @staticmethod
    def trend_strength(prices):
        return float(np.polyfit(range(len(prices)), prices, 1)[0])
