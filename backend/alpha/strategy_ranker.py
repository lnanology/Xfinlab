
class StrategyRanker:
    @staticmethod
    def rank(strategies):
        ranked = sorted(strategies, key=lambda x: x["alpha_score"], reverse=True)
        return {"best_strategy": ranked[0] if ranked else None, "all": ranked}
