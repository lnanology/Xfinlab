
import random

class BacktestEngine:
    @staticmethod
    def run(strategy):
        return random.uniform(-1, 1) * strategy["weight"]
