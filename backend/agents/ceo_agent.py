
class CEOAgent:
    @staticmethod
    def decide(inputs):
        score = inputs.get("market_score", 50)
        if score > 70:
            return "AGGRESSIVE_GROWTH"
        elif score < 40:
            return "DEFENSIVE"
        return "NEUTRAL"
