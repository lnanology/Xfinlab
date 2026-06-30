class ScoringEngine:

    @classmethod
    def calculate(
        cls,
        market_score,
        news_score,
        strategy_score,
        overall_risk
    ):

        final_score = (
            market_score * 0.30 +
            news_score * 0.25 +
            strategy_score * 0.30 +
            (100 - overall_risk) * 0.15
        )

        final_score = round(final_score, 2)

        if final_score >= 85:
            rating = "STRONG BUY"
        elif final_score >= 70:
            rating = "BUY"
        elif final_score >= 50:
            rating = "HOLD"
        else:
            rating = "SELL"

        return {
            "final_score": final_score,
            "rating": rating
        }