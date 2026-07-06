
import numpy as np

class FactorLibrary:
    @staticmethod
    def momentum(prices):
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
