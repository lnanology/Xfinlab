
import numpy as np

class PortfolioOptimizer:
    @staticmethod
    def optimize(expected_returns, risk):
        weights = np.array(expected_returns) / (np.array(risk) + 1e-6)
        weights = weights / np.sum(weights)
        return {"weights": weights.tolist(), "expected_return": float(np.sum(weights * expected_returns))}
