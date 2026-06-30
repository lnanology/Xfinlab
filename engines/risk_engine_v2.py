"""
XFINLAB Risk Engine
Calculates overall risk based on volatility, event risk, and news score
"""

from typing import Dict


class RiskEngine:
    """Calculates market risk from multiple inputs"""

    @staticmethod
    def calculate(volatility: float, event_risk: float, news_score: float) -> Dict:
        """
        Calculate overall risk level

        Args:
            volatility: Market volatility (0-100)
            event_risk: Event-based risk score (0-100)
            news_score: News sentiment score (0-100)

        Returns:
            Dict with overall_risk, risk_level, and breakdown
        """
        # News risk is inverse of news score
        news_risk = 100 - news_score

        # Weighted average
        overall_risk = round(
            (volatility * 0.4) +
            (event_risk * 0.3) +
            (news_risk * 0.3),
            2
        )

        # Cap between 0-100
        overall_risk = max(0, min(100, overall_risk))

        if overall_risk < 30:
            risk_level = "Low Risk"
        elif overall_risk < 60:
            risk_level = "Medium Risk"
        else:
            risk_level = "High Risk"

        return {
            "overall_risk": overall_risk,
            "risk_level": risk_level,
            "breakdown": {
                "volatility": volatility,
                "event_risk": event_risk,
                "news_risk": round(news_risk, 2)
            }
        }
