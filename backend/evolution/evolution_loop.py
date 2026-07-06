
from evolution.strategy_pool import StrategyPool
from evolution.mutation_engine import MutationEngine
from evolution.backtest_engine import BacktestEngine
from evolution.fitness_evaluator import FitnessEvaluator

class EvolutionLoop:
    def __init__(self):
        self.pool = StrategyPool()

    def run(self, generations=5):
        population = self.pool.get_all()
        for _ in range(generations):
            new_population = []
            for strategy in population:
                mutated = MutationEngine.mutate(strategy)
                performance = BacktestEngine.run(mutated)
                score = FitnessEvaluator.score(performance)
                mutated["score"] = score
                new_population.append(mutated)
            population = sorted(new_population, key=lambda x: x["score"], reverse=True)[:max(1, len(new_population)//2)]
        return population
