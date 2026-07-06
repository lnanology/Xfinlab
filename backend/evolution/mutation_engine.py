
import random

class MutationEngine:
    @staticmethod
    def mutate(strategy):
        new_strategy = strategy.copy()
        new_strategy["weight"] = max(0.1, new_strategy["weight"] + random.uniform(-0.3, 0.3))
        return new_strategy
