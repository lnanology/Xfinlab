
class StrategyPool:
    def __init__(self):
        self.strategies = [
            {"name": "momentum", "weight": 1.0},
            {"name": "mean_reversion", "weight": 1.0},
            {"name": "volatility_breakout", "weight": 1.0}
        ]
    def get_all(self):
        return self.strategies
