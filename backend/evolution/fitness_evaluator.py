
class FitnessEvaluator:
    @staticmethod
    def score(performance):
        return max(0, performance + 1)
