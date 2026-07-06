
import numpy as np
from quant.factor_library import FactorLibrary

class FactorEngine:
    @staticmethod
    def calculate(market_data: dict):
        prices = np.array(market_data.get("prices", [100, 101, 102]))
        returns = np.diff(prices)
        factors = {
            "momentum": FactorLibrary.momentum(prices),
            "volatility": FactorLibrary.volatility(returns),
            "trend": FactorLibrary.trend_strength(prices),
            "mean_reversion": FactorLibrary.mean_reversion(prices)
        }
        score = (
            factors["momentum"] * 40 +
            (1 - factors["volatility"]) * 30 +
            factors["trend"] * 20 +
            (1 - abs(factors["mean_reversion"])) * 10
        )
        return {"factors": factors, "factor_score": float(score)}
