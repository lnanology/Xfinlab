
class SignalEngine:
    @staticmethod
    def generate(decision):
        score = decision.get("final_score", 50)
        if score >= 70:
            return "BUY"
        elif score <= 40:
            return "SELL"
        return "HOLD"
