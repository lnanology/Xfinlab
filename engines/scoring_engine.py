"""
XFINLAB Scoring Engine
Calculates final investment score and rating
"""

from typing import Dict


class ScoringEngine:
    """Calculates final investment score from multiple inputs"""

    @staticmethod
    def calculate(
        market_score: float,
        news_score: float,
        strategy_score: float,
        overall_risk: float
    ) -> Dict:
        """
        Calculate final investment score and rating

        Args:
            market_score: Market data score (0-100)
            news_score: News sentiment score (0-100)
            strategy_score: Strategy engine score (0-100)
            overall_risk: Risk score (0-100, higher = more risk)

        Returns:
            Dict with final_score and rating
        """
        # Risk penalty (higher risk = lower score)
        risk_penalty = overall_risk * 0.2

        # Weighted score
        raw_score = (
            (market_score * 0.35) +
            (news_score * 0.25) +
            (strategy_score * 0.40)
        )

        final_score = round(max(0, min(100, raw_score - risk_penalty)), 2)

        if final_score >= 80:
            rating = "Strong Buy"
        elif final_score >= 65:
            rating = "Buy"
        elif final_score >= 50:
            rating = "Neutral"
        elif final_score >= 35:
            rating = "Sell"
        else:
            rating = "Strong Sell"

        return {
            "final_score": final_score,
            "rating": rating,
            "breakdown": {
                "market_score": market_score,
                "news_score": news_score,
                "strategy_score": strategy_score,
                "risk_penalty": round(risk_penalty, 2)
            }
        }
