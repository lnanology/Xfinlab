
class Planner:
    @staticmethod
    def plan(context):
        score = context.get("market_score", 50)
        if score > 75:
            return "AGGRESSIVE_EXPAND"
        elif score < 40:
            return "DEFENSIVE_MODE"
        return "BALANCED_MODE"
