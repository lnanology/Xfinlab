
class Committee:
    @staticmethod
    def vote(ceo, analyst, risk, portfolio):
        score = 0
        if ceo == "AGGRESSIVE_GROWTH":
            score += 40
        elif ceo == "DEFENSIVE":
            score -= 40
        score += analyst["confidence"] * 30
        if risk["risk"] == "HIGH":
            score -= 20
        score += portfolio["allocation_score"] * 20
        if score > 60:
            return "BUY"
        elif score < 40:
            return "SELL"
        return "HOLD"
