
class JudgeAgent:
    @staticmethod
    def decide(news, risk, strategy):
        score = (
            news["score"] * 0.4 +
            (100 - risk["risk_score"]) * 0.3 +
            strategy["confidence"] * 100 * 0.3
        )
        if score > 70:
            verdict = "STRONG BUY"
        elif score > 55:
            verdict = "BUY"
        elif score > 45:
            verdict = "HOLD"
        else:
            verdict = "SELL"
        return {"final_score": score, "verdict": verdict}
