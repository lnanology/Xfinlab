"""
Risk Engine Module - Evaluates market risk based on volatility.

This is the ONE canonical RiskEngine for the whole codebase (every real
caller -- api/ai_analysis.py, api/hero_showcase.py, api/full_analysis_v3.py,
api/analysis_api.py, backend/core/pipeline.py, services/dashboard_
snapshot_service.py -- imports from here: `from engines.risk_engine import
RiskEngine`).

2026-07-18 consolidation note: two other near-duplicate copies used to
exist (engines/risk_engine_v2.py and backend/engines/risk_engine.py) --
both were dead code (grepped: zero real importers anywhere in the repo,
only this file was ever actually imported) and have been deleted. If you
need a risk calculation anywhere, import THIS module; don't create a new
risk_engine variant.
"""

from typing import Dict


class RiskEngine:
    """Assesses market risk level based on volatility input"""

    def assess(self, volatility: float) -> Dict:
        """Original method - kept for backward compatibility"""
        if volatility < 20:
            risk_level = "Low Risk"
        elif volatility <= 40:
            risk_level = "Medium Risk"
        else:
            risk_level = "High Risk"
        return {"volatility": volatility, "risk_level": risk_level}

    @classmethod
    def calculate(cls, volatility=20, event_risk=20, news_score=50) -> Dict:
        """Calculate overall risk from multiple inputs"""
        market_risk = max(0, min(volatility, 100))
        news_risk = 100 - news_score
        overall_risk = round(
            market_risk * 0.4 +
            event_risk * 0.3 +
            news_risk * 0.3,
            2
        )
        if overall_risk < 35:
            risk_level = "LOW"
        elif overall_risk < 65:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"
        return {
            "market_risk": market_risk,
            "event_risk": event_risk,
            "news_risk": news_risk,
            "overall_risk": overall_risk,
            "risk_level": risk_level
        }
